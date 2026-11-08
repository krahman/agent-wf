# Proposal

## Why

The Wikipedia tool depends on `langchain-community`, which its maintainers have announced they are sunsetting (every test run prints the deprecation warning), and on the unmaintained `wikipedia` package, whose private `_wiki_request` function our code monkeypatches to add a User-Agent and a timeout. Together they pull in a large dependency tree (`sqlalchemy`, `numpy`, `aiohttp`, `langchain-classic` and more) for what is, in effect, one search request, and a single lookup takes about 2.9 s because the wrapper makes several requests per page. The tool is also unreliable today: while capturing a baseline, the current tool failed on two of three queries ("Mercury" and a nonsense query) because Wikipedia rate-limits (429) requests whose User-Agent is only `agent_wf/0.1.0`. Replacing everything with one direct call that identifies itself properly removes the warning and the fragile patch, and makes the tool faster, smaller and more reliable.

## What Changes

- Rewrite the Wikipedia tool to make **one** request to Wikipedia's search API per lookup, using `httpx` (already installed through `fastapi[standard]`), and format the result exactly as before: up to 3 pages, each `Page: <title>\nSummary: <intro text>`, separated by blank lines, capped at 4000 characters.
- Keep the tool's contract with the agent unchanged: name `search_wikipedia`, argument `query`, the same description, and the same `{"result": ...}` / `{"error": ...}` return shape.
- Keep the existing behaviour for edge cases: disambiguation pages are skipped, and no match returns the same "no good result" message.
- Make the request's limits explicit and tested: a 10 s timeout, up to 3 attempts for transient failures, queries cut to 300 characters, and a User-Agent that names the application, its version and a project URL. The URL is needed: a probe showed Wikipedia answers `httpx` with a plain `agent_wf/0.1.0` User-Agent with **403**, while one that includes a URL gets 200 (Wikimedia's policy asks for contact information). It defaults to this project's repository and is configurable through a new `WIKIPEDIA_CONTACT` setting.
- Remove `langchain-community` and `wikipedia` from the dependencies and add `httpx` explicitly (the code imports it directly); the lockfile shrinks accordingly.
- Point the eval suite's Wikipedia stub at the tool's new network seam instead of at `WikipediaAPIWrapper`, so evals still run the real tool code and only replace the network call.
- Add unit tests for the tool, which currently has none, using a mocked HTTP transport so they run offline.

Out of scope, with the reason:
- The other warning (`langsmith` calling a function Python 3.16 will remove): it comes from a library the project does not control and will go away with an upstream update.
- Changing what the agent is told about the tool, caching lookups, other languages or other Wikimedia projects.
- Updating `examples/AI-Math-Assistant Tool Calling.ipynb`, which still imports `langchain_community` in its own course-material setup.

## Capabilities

### New Capabilities
- `wikipedia-lookup`: how the agent's Wikipedia lookup tool answers a query: the result format and limits, what it skips, and how it reports failures. It describes behaviour that exists today but is not written down, so the migration can be checked against it.

### Modified Capabilities

None. The existing specs are unaffected, and `agent-evals` is only touched at the implementation level (which function the stub replaces), with no change to its requirements.

## Impact

- Code: `src/agent_wf/tools/wikipedia.py` (rewritten); `src/agent_wf/config.py` and `.env.example` (the new `WIKIPEDIA_CONTACT` setting); `tests/evals/support.py` and `tests/test_eval_support.py` (the stub's target); new `tests/test_wikipedia_tool.py`; `AGENTS.md` (the evals note about the stub).
- Dependencies: remove `langchain-community` and `wikipedia`, add `httpx`; `uv.lock` changes substantially (several transitive packages disappear, so the Docker image also gets smaller).
- Behaviour the agent sees: the same text for the same pages, from one request instead of several; lookups become faster (about 0.5 s measured against 2.9 s).
- Risks to check: Wikipedia's API response shape and the equivalence of its intro extracts with what the old package returned (the comparison against the old output and a real eval run cover this), and Wikimedia's User-Agent rule, which can turn a careless change into 403 errors (a live check against the real API is part of the tasks).
- CI is unaffected (default tests stay offline and the lint and docker jobs run as before).
