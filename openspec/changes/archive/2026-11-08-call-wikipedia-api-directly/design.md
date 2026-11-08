# Design

## Context

See proposal.md for motivation and the `wikipedia-lookup` spec for required behaviour. What exists today, verified in the code:

- `tools/wikipedia.py` calls `WikipediaAPIWrapper().run(query)` from `langchain-community`. That wrapper searches the top 3 titles, fetches each page through the `wikipedia` package (`page(title, auto_suggest=False)`, skipping `PageError` and `DisambiguationError`), formats `Page: <title>\nSummary: <summary>`, joins with blank lines, cuts to 4000 characters, and returns "No good Wikipedia Search Result was found" when nothing is usable. Queries are cut to 300 characters.
- Our tool monkeypatches `wikipedia.wikipedia._wiki_request` (a private function) to add a User-Agent, a timeout and 3 retries, on first use.
- Nothing else in `src/` or `tests/` uses `langchain_community`, except the eval stub (`tests/evals/support.py`) and its test, which patch `WikipediaAPIWrapper.run`. The Wikipedia tool has no unit tests of its own.
- The agent sees: name `search_wikipedia`, argument `query`, description "Search Wikipedia for factual information about a topic and return a summary."

Facts measured against the live API while planning:
- One request with `generator=search` and `prop=extracts|pageprops` (`exintro`, `explaintext`, `ppprop=disambiguation`) returns the top 3 pages with their intro text and a disambiguation flag, ranked by an `index` field. It took about 0.5 s, against about 2.9 s for the current wrapper on the same query, with the same intro text.
- A nonsense query returns an empty result; "Mercury" returns a disambiguation page first.
- **Wikimedia returns 403 (an HTML error page, not JSON) to `httpx` when the User-Agent is just `agent_wf/0.1.0`**, but 200 when it includes a project URL. The same plain string worked from `requests`, so the rule depends on the client as well as the string. This is Wikimedia's policy that User-Agents carry contact information.

## Goals / Non-Goals

**Goals:**
- Remove `langchain-community` and `wikipedia` with no change to what the agent is told or to the text it gets for the same pages.
- A tool whose HTTP behaviour (limits, retries, error handling) is explicit and tested offline.

**Non-Goals:**
- Caching, other languages, other Wikimedia projects, changing the tool's description, or touching the `langsmith` warning (see proposal).

## Decisions

**1. One request using the search generator.**
`action=query&generator=search&gsrsearch=<query>&gsrlimit=3&prop=extracts|pageprops&exintro=1&explaintext=1&exlimit=3&ppprop=disambiguation&format=json&formatversion=2`. Pages are sorted by `index` to keep Wikipedia's ranking. Alternatives: search, then one summary request per page (N+1 requests); the `wikipedia` package (several requests per page); Wikimedia's REST summary endpoint (a shorter lead than the full intro the old tool returned).

**2. A small network seam, `fetch_pages`, separate from formatting.**
`fetch_pages(query, client=None) -> list[Page]` does the HTTP, parsing, and skipping of disambiguation and empty pages. The tool function only formats (`Page: ...\nSummary: ...`, blank-line joins, 4000-character cut, the no-result message) and converts failures into `{"error": ...}`. The eval stub replaces only `fetch_pages`, so evals still exercise the real tool name, description, schema and formatting. Unit tests drive `fetch_pages` with an `httpx.MockTransport` through the `client` argument, and the tool with a patched `fetch_pages`.

**3. `httpx`, declared as a direct dependency.**
It is already installed through `fastapi[standard]`, so no new package arrives; the code now imports it directly, so `pyproject.toml` lists it. The tool is synchronous (LangChain runs sync tools in a worker thread for the async API), so `httpx.Client`/`httpx.get` fits. Alternative: `requests`, which was only available transitively and is not otherwise needed.

**4. Retry policy: 3 attempts, only for transient failures, status checked before the body is parsed.**
Retry on `httpx.TransportError` (which includes timeouts), HTTP 429 and 5xx, and an unparseable body on a 200; wait 1 s between attempts (as today). Any other 4xx, including the 403 above, fails after one attempt. The status is checked before parsing because the 403 body is HTML. The sleep is a module-level function tests can replace. Alternatives: `tenacity` (another import for ten lines); transport-level retries in `httpx` (connection errors only, no 5xx or 429).

**5. User-Agent `agent_wf/<version> (+<contact>)`, contact URL from a new setting.**
`Settings.wikipedia_contact` (env `WIKIPEDIA_CONTACT`) defaults to this project's repository URL, so the tool works out of the box, and a fork or deployment can put its own contact there. The value is read when a request is made, not at import. Alternatives: hard-code the URL (no way for operators to change it); derive it from package metadata (needs `[project.urls]` and more code).

**6. Defensive parsing.**
A response that is valid JSON but lacks the expected `query.pages` structure is treated as an unreadable response (retried, then an error), except that an absent `query` key with a valid body means "no results" (the API omits `query` when nothing matches, which the nonsense-query probe confirmed returns an empty result). Pages without an `extract`, or flagged `disambiguation`, are dropped.

**7. Constants in one place.**
`TOP_K = 3`, `MAX_QUERY_CHARS = 300`, `MAX_RESULT_CHARS = 4000`, `TIMEOUT = 10`, `ATTEMPTS = 3`, matching the old wrapper's numbers, so the spec's figures live in code as named values.

## Risks / Trade-offs

- [Wikimedia's User-Agent rule: a generic User-Agent gets 403 depending on the client] → The default includes a project URL; the URL is configurable; a 403 is returned to the agent as a clear error instead of crashing; the tasks include a live check against the real API, which would catch a regression at once.
- [The intro text or ranking differs slightly from the old wrapper's] → The tasks capture the old tool's output for three queries before changing anything and compare it with the new output; a real eval run then checks the agent's behaviour.
- [Wikipedia changes its API response shape] → Defensive parsing turns unexpected shapes into an error value, not an exception; unit tests pin the shapes we rely on.
- [Rate limiting at higher volume] → 429 is retried with a 1 s pause; volume is low today, and caching is a later option.
- [The offline tests cannot prove the live API still behaves as assumed] → The live comparison is a deliberate manual task, and the AGENTS.md note tells future maintainers to re-run it after touching the tool.
- [The example notebook still imports `langchain_community`] → It is course material with its own setup and is excluded from linting; noted as out of scope.

## Migration Plan

Single change, no data. Rollback is a revert of the commit; the old dependencies are restored by the lockfile. After merging, nothing needs to be done by callers: the tool's interface and output format are unchanged.

## Open Questions

None that would change the specs, the approach or the tasks.
