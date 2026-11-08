"""The opt-in tracing preflight: what stops a run, and that nothing happens without the flag."""

from datetime import UTC, datetime

import httpx
import pytest

from agent_wf.config import Settings
from tests.evals import tracing
from tests.evals.report import run_id, run_metadata, write_report

SECRET = "sk-lf-very-secret-value"


def settings(**kw):
    base = {"langfuse_public_key": "pk-lf-1", "langfuse_secret_key": SECRET, "langfuse_host": "http://lf.test:3000"}
    return Settings(_env_file=None, **{**base, **kw})


def health(monkeypatch, response=None, error=None):
    """Replace the health probe; returns the list of (url, kwargs) it was called with."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if error:
            raise error
        return response or httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(tracing.httpx, "get", fake_get)
    return calls


def exit_message(callable_, *args):
    with pytest.raises(pytest.exit.Exception) as exc:
        callable_(*args)
    assert exc.value.returncode == 2
    return str(exc.value)


# --- the keys


def test_missing_public_key_is_named_and_the_secret_is_not_printed(monkeypatch):
    calls = health(monkeypatch)
    message = exit_message(tracing.require_langfuse, settings(langfuse_public_key=None))
    assert "LANGFUSE_PUBLIC_KEY" in message and "LANGFUSE_SECRET_KEY" not in message
    assert SECRET not in message
    assert calls == [], "no request before the configuration is complete"


def test_missing_secret_key_is_named(monkeypatch):
    health(monkeypatch)
    message = exit_message(tracing.require_langfuse, settings(langfuse_secret_key=None))
    assert "LANGFUSE_SECRET_KEY" in message and "LANGFUSE_PUBLIC_KEY" not in message


def test_both_missing_keys_are_named(monkeypatch):
    health(monkeypatch)
    message = exit_message(tracing.require_langfuse, settings(langfuse_public_key=None, langfuse_secret_key=None))
    assert "LANGFUSE_PUBLIC_KEY" in message and "LANGFUSE_SECRET_KEY" in message


# --- the server


def test_unreachable_server_is_named_by_address(monkeypatch):
    health(monkeypatch, error=httpx.ConnectError("refused"))
    message = exit_message(tracing.require_langfuse, settings())
    assert "http://lf.test:3000" in message and "not reachable" in message
    assert SECRET not in message


@pytest.mark.parametrize("status", [500, 502, 404])
def test_a_server_that_answers_with_an_error_counts_as_unreachable(monkeypatch, status):
    url = "http://lf.test:3000/api/public/health"
    health(monkeypatch, response=httpx.Response(status, request=httpx.Request("GET", url)))
    assert "not reachable" in exit_message(tracing.require_langfuse, settings())


def test_a_timeout_counts_as_unreachable(monkeypatch):
    health(monkeypatch, error=httpx.ReadTimeout("slow"))
    assert "not reachable" in exit_message(tracing.require_langfuse, settings())


def test_a_malformed_host_counts_as_unreachable(monkeypatch):
    health(monkeypatch, error=httpx.InvalidURL("bad"))
    assert "not reachable" in exit_message(tracing.require_langfuse, settings(langfuse_host="not a url"))


def test_a_healthy_server_passes_and_is_probed_quickly(monkeypatch):
    calls = health(monkeypatch)
    tracing.require_langfuse(settings(langfuse_host="http://lf.test:3000/"))
    [(url, kwargs)] = calls
    assert url == "http://lf.test:3000/api/public/health" and kwargs["timeout"] == 3


# --- the flag


def test_without_the_flag_nothing_is_configured_and_nothing_is_requested(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not be called without --eval-trace")

    monkeypatch.setattr(tracing.httpx, "get", forbidden)
    monkeypatch.setattr(tracing, "configure_tracing", forbidden)
    assert tracing.start_tracing(False, settings(langfuse_public_key=None)) is False


def test_the_flag_forces_tracing_on_even_when_the_configuration_says_off(monkeypatch):
    health(monkeypatch)
    seen = []
    monkeypatch.setattr(tracing, "configure_tracing", seen.append)
    original = settings(langfuse_tracing=False)
    assert tracing.start_tracing(True, original) is True
    [passed] = seen
    assert passed.langfuse_tracing is True
    assert passed.langfuse_host == original.langfuse_host and passed.langfuse_public_key == "pk-lf-1"
    assert original.langfuse_tracing is False, "the caller's settings are not modified"


def test_the_flag_without_keys_stops_before_configuring(monkeypatch):
    health(monkeypatch)
    monkeypatch.setattr(tracing, "configure_tracing", lambda s: pytest.fail("configured without keys"))
    assert "LANGFUSE_PUBLIC_KEY" in exit_message(tracing.start_tracing, True, settings(langfuse_public_key=None))


# --- one run id for the report file and the Langfuse session


def test_run_id_names_the_run_by_start_time_and_model():
    started = datetime(2026, 11, 8, 9, 46, 12, tzinfo=UTC)
    assert run_id(started, "openai/gpt-4o") == "20261108T094612Z-openai-gpt-4o"


def test_the_report_file_is_named_by_the_run_id(tmp_path):
    started = datetime(2026, 11, 8, 9, 46, 12, tzinfo=UTC)
    meta = run_metadata(Settings(_env_file=None, git_sha="abc"), "openai/gpt-4o", 3, 1.0, started)
    assert meta["started_at"] == "2026-11-08T09:46:12+00:00"
    path = write_report({**meta, "passed": True, "cases": []}, tmp_path)
    assert path.stem == run_id(started, "openai/gpt-4o")
