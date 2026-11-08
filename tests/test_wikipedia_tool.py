"""The Wikipedia tool against a mocked HTTP transport: offline, and no real sleeping."""

import importlib
import socket

import httpx
import pytest

import agent_wf.tools.wikipedia as wiki
from agent_wf import __version__
from agent_wf.config import get_settings


def page(title, extract="Some introduction.", index=1, disambiguation=False):
    p = {"pageid": index, "title": title, "index": index}
    if extract is not None:
        p["extract"] = extract
    if disambiguation:
        p["pageprops"] = {"disambiguation": ""}
    return p


def ok(*pages):
    return httpx.Response(200, json={"batchcomplete": True, "query": {"pages": list(pages)}})


class Server:
    """Replays queued responses (or raises queued exceptions) and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))

    def fetch(self, query="q"):
        return wiki.fetch_pages(query, client=self.client)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    pauses = []
    monkeypatch.setattr(wiki, "_sleep", pauses.append)
    return pauses


@pytest.fixture
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- the request


def test_one_request_with_the_documented_parameters():
    server = Server(ok(page("Eiffel Tower")))
    server.fetch("Eiffel Tower")
    assert len(server.requests) == 1
    request = server.requests[0]
    assert str(request.url).startswith("https://en.wikipedia.org/w/api.php?")
    params = dict(request.url.params)
    assert params == {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrsearch": "Eiffel Tower", "gsrlimit": "3",
        "prop": "extracts|pageprops", "exintro": "1", "explaintext": "1", "exlimit": "3",
        "ppprop": "disambiguation",
    }


def test_each_request_has_a_10_second_timeout():
    server = Server(ok(page("A")))
    server.fetch()
    assert server.requests[0].extensions["timeout"]["read"] == 10


def test_long_queries_are_cut_to_300_characters():
    server = Server(ok(page("A")))
    server.fetch("x" * 1000)
    assert dict(server.requests[0].url.params)["gsrsearch"] == "x" * 300


def test_user_agent_names_app_version_and_project_url(fresh_settings):
    server = Server(ok(page("A")))
    server.fetch()
    agent = server.requests[0].headers["user-agent"]
    assert agent.startswith(f"agent_wf/{__version__} (+https://")
    assert get_settings().wikipedia_contact in agent


def test_configured_contact_replaces_the_default(monkeypatch, fresh_settings):
    monkeypatch.setenv("WIKIPEDIA_CONTACT", "ops@example.com")
    get_settings.cache_clear()
    server = Server(ok(page("A")))
    server.fetch()
    assert server.requests[0].headers["user-agent"] == f"agent_wf/{__version__} (+ops@example.com)"


# --- reading the response


def test_pages_are_returned_in_ranking_order_whatever_the_response_order():
    pages = [page("Third", index=3), page("First", index=1), page("Second", index=2)]
    assert [p.title for p in Server(ok(*pages)).fetch()] == ["First", "Second", "Third"]


def test_disambiguation_and_empty_pages_are_skipped():
    server = Server(ok(
        page("Mercury", "Mercury most commonly refers to:", index=1, disambiguation=True),
        page("Blank", "   ", index=2),
        page("No extract", None, index=3),
        page("Mercury (planet)", "The first planet.", index=4),
    ))
    assert [(p.title, p.summary) for p in server.fetch()] == [("Mercury (planet)", "The first planet.")]


def test_summary_whitespace_is_trimmed():
    [p] = Server(ok(page("A", "  text\n"))).fetch()
    assert p.summary == "text"


@pytest.mark.parametrize("body", [{"batchcomplete": True}, {"batchcomplete": True, "query": {"pages": []}}])
def test_no_match_returns_no_pages(body):
    assert Server(httpx.Response(200, json=body)).fetch() == []


# --- the tool: format, limits, no-result message


def test_tool_formats_pages(monkeypatch):
    monkeypatch.setattr(wiki, "fetch_pages", lambda q: [wiki.Page("A", "one"), wiki.Page("B", "two")])
    out = wiki.search_wikipedia.invoke({"query": "x"})
    assert out == {"result": "Page: A\nSummary: one\n\nPage: B\nSummary: two"}


def test_tool_cuts_the_result_to_exactly_4000_characters(monkeypatch):
    monkeypatch.setattr(wiki, "fetch_pages", lambda q: [wiki.Page("A", "x" * 3000), wiki.Page("B", "y" * 3000)])
    result = wiki.search_wikipedia.invoke({"query": "x"})["result"]
    assert len(result) == 4000 and result.startswith("Page: A\nSummary: xxx")


def test_tool_reports_no_match(monkeypatch):
    monkeypatch.setattr(wiki, "fetch_pages", lambda q: [])
    assert wiki.search_wikipedia.invoke({"query": "zzz"}) == {"result": "No good Wikipedia Search Result was found"}


def test_tool_returns_an_error_value_instead_of_raising(monkeypatch):
    def boom(q):
        raise wiki.WikipediaError("HTTP 403")

    monkeypatch.setattr(wiki, "fetch_pages", boom)
    assert wiki.search_wikipedia.invoke({"query": "x"}) == {"error": "Wikipedia lookup failed: HTTP 403"}


def test_tool_survives_an_unexpected_exception(monkeypatch):
    def boom(q):
        raise RuntimeError("bug")

    monkeypatch.setattr(wiki, "fetch_pages", boom)
    assert wiki.search_wikipedia.invoke({"query": "x"}) == {"error": "Wikipedia lookup failed: bug"}


# --- retries and failures


def test_transient_failure_then_success(no_sleep):
    server = Server(httpx.Response(503), ok(page("A")))
    assert [p.title for p in server.fetch()] == ["A"]
    assert len(server.requests) == 2 and no_sleep == [1.0]


def test_rate_limiting_is_retried():
    server = Server(httpx.Response(429), ok(page("A")))
    assert len(server.fetch()) == 1 and len(server.requests) == 2


def test_three_failed_attempts_then_an_error_and_no_fourth(no_sleep):
    server = Server(httpx.Response(500))
    with pytest.raises(wiki.WikipediaError, match="HTTP 500.*3 attempts"):
        server.fetch()
    assert len(server.requests) == 3 and no_sleep == [1.0, 1.0]


def test_timeouts_and_network_errors_are_retried_then_reported():
    server = Server(httpx.ReadTimeout("slow"))
    with pytest.raises(wiki.WikipediaError, match="3 attempts"):
        server.fetch()
    assert len(server.requests) == 3
    server = Server(httpx.ConnectError("down"), httpx.ConnectError("down"), ok(page("A")))
    assert len(server.fetch()) == 1


@pytest.mark.parametrize("status", [403, 404, 400])
def test_client_errors_are_not_retried_and_the_body_is_not_parsed(status, monkeypatch):
    def parsed(self, *a, **k):
        raise AssertionError("an error response must not be parsed as data")

    monkeypatch.setattr(httpx.Response, "json", parsed)
    server = Server(httpx.Response(status, text="<html>Wikimedia Error</html>"))
    with pytest.raises(wiki.WikipediaError, match=f"HTTP {status}"):
        server.fetch()
    assert len(server.requests) == 1


def test_unreadable_body_is_retried_then_reported():
    server = Server(httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(wiki.WikipediaError, match="unreadable response"):
        server.fetch()
    assert len(server.requests) == 3


@pytest.mark.parametrize("body", [{"query": {"pages": "nope"}}, {"query": []}, ["list"]])
def test_unexpected_shape_is_retried_then_reported(body):
    server = Server(httpx.Response(200, json=body))
    with pytest.raises(wiki.WikipediaError, match="unexpected response shape"):
        server.fetch()
    assert len(server.requests) == 3


def test_api_error_body_is_reported_without_retrying():
    server = Server(httpx.Response(200, json={"error": {"code": "badvalue", "info": "secret detail"}}))
    with pytest.raises(wiki.WikipediaError, match="badvalue") as exc:
        server.fetch()
    assert "secret detail" not in str(exc.value) and len(server.requests) == 1


# --- the interface the agent sees


def test_tool_interface_is_unchanged():
    tool = wiki.search_wikipedia
    assert tool.name == "search_wikipedia"
    assert tool.description == "Search Wikipedia for factual information about a topic and return a summary."
    assert sorted(tool.args) == ["query"] and tool.args["query"]["type"] == "string"
    assert wiki.wikipedia_tools == [tool]


def test_loading_the_module_touches_no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access at import time")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    importlib.reload(wiki)
