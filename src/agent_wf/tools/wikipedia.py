import logging
import time
from dataclasses import dataclass

import httpx
from langchain_core.tools import tool

from agent_wf import __version__
from agent_wf.config import get_settings

logger = logging.getLogger("agent_wf.tools")

API_URL = "https://en.wikipedia.org/w/api.php"
TOP_K = 3
MAX_QUERY_CHARS = 300
MAX_RESULT_CHARS = 4000
TIMEOUT = 10  # seconds, per request
ATTEMPTS = 3
RETRY_PAUSE = 1.0  # seconds between attempts
NO_RESULT = "No good Wikipedia Search Result was found"


@dataclass(frozen=True)
class Page:
    title: str
    summary: str


class WikipediaError(Exception):
    """A lookup that could not be completed; the message is safe to show the agent."""


class _Transient(Exception):
    """A failure worth another attempt."""


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _user_agent() -> str:
    # Wikimedia rate-limits or blocks callers that do not identify themselves with contact information.
    return f"agent_wf/{__version__} (+{get_settings().wikipedia_contact})"


def _parse(body: object) -> list[Page]:
    if not isinstance(body, dict):
        raise _Transient("unexpected response shape")
    if "error" in body:
        error = body["error"] if isinstance(body["error"], dict) else {}
        raise WikipediaError(f"Wikipedia API error: {error.get('code', 'unknown')}")
    query = body.get("query")
    if query is None:
        return []  # the API omits `query` when nothing matches
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, list):
        raise _Transient("unexpected response shape")
    found = []
    for page in sorted(pages, key=lambda p: p.get("index", len(pages))):
        summary = (page.get("extract") or "").strip()
        if "disambiguation" in page.get("pageprops", {}) or not summary:
            continue
        found.append(Page(page["title"], summary))
    return found


def fetch_pages(query: str, client: httpx.Client | None = None) -> list[Page]:
    """Search Wikipedia once and return the top pages' intro text, best match first."""
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": query[:MAX_QUERY_CHARS],
        "gsrlimit": TOP_K,
        "prop": "extracts|pageprops",
        "exintro": 1,
        "explaintext": 1,
        "exlimit": TOP_K,
        "ppprop": "disambiguation",
    }
    headers = {"User-Agent": _user_agent()}
    owns_client = client is None
    client = client or httpx.Client()
    try:
        last: Exception | None = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = client.get(API_URL, params=params, headers=headers, timeout=TIMEOUT)
                status = response.status_code
                if status == 429 or status >= 500:
                    raise _Transient(f"HTTP {status}")
                if status >= 400:
                    raise WikipediaError(f"HTTP {status}")  # e.g. 403: the body is HTML, not data
                try:
                    body = response.json()
                except ValueError:
                    raise _Transient("unreadable response") from None
                return _parse(body)
            except (httpx.TransportError, _Transient) as exc:
                last = exc
                if attempt < ATTEMPTS:
                    _sleep(RETRY_PAUSE)
        raise WikipediaError(f"{last} (gave up after {ATTEMPTS} attempts)")
    finally:
        if owns_client:
            client.close()


def format_pages(pages: list[Page]) -> str:
    text = "\n\n".join(f"Page: {p.title}\nSummary: {p.summary}" for p in pages)
    return text[:MAX_RESULT_CHARS]


@tool
def search_wikipedia(query: str) -> dict:
    """Search Wikipedia for factual information about a topic and return a summary."""
    try:
        pages = fetch_pages(query)
    except Exception as e:
        logger.warning("wikipedia lookup failed: %s", e, exc_info=True)
        return {"error": f"Wikipedia lookup failed: {e}"}
    return {"result": format_pages(pages) if pages else NO_RESULT}


wikipedia_tools = [search_wikipedia]
