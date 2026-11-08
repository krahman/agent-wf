import time

import requests
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool
from wikipedia import wikipedia as wp

API_URL = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 10
_patched = False


def _wiki_request(params, _retries=3):
    params["format"] = "json"
    params.setdefault("action", "query")
    headers = {"User-Agent": "agent_wf/0.1.0"}

    last_exc: Exception | None = None
    for attempt in range(_retries):
        try:
            return requests.get(API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT).json()
        except (ValueError, requests.RequestException) as e:
            last_exc = e
            if attempt < _retries - 1:
                time.sleep(1)
    raise last_exc


def _ensure_patched() -> None:
    """Patch the `wikipedia` library on first use rather than at import time."""
    global _patched
    if not _patched:
        wp.API_URL = API_URL
        wp._wiki_request = _wiki_request
        _patched = True


@tool
def search_wikipedia(query: str) -> dict:
    """Search Wikipedia for factual information about a topic and return a summary."""
    _ensure_patched()
    try:
        return {"result": WikipediaAPIWrapper().run(query)}
    except Exception as e:  # noqa: BLE001 - any failure goes back to the LLM as a tool error
        return {"error": f"Wikipedia lookup failed: {e}"}


wikipedia_tools = [search_wikipedia]
