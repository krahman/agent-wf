# Tasks

## 1. Baseline and setting

- [x] 1.1 Before changing any code, run the current tool for "Eiffel Tower", "Mercury" and "asdkjhqwe zzzxxyy" and save each output with its latency, plus the tool's name, description and argument names, to the scratchpad; verify the three output files and the interface file exist and are non-empty
- [x] 1.2 Add `wikipedia_contact` to `Settings` (default: this project's repository URL) and to `.env.example`; verify unit tests cover the default, an override through `WIKIPEDIA_CONTACT`, and an empty value being treated as unset

## 2. Tool rewrite

- [x] 2.1 Rewrite `src/agent_wf/tools/wikipedia.py`: a `Page` type; `fetch_pages(query, client=None)` making one request with the parameters in design decision 1, sorting by `index`, skipping disambiguation and empty pages, with a 10 s timeout, up to 3 attempts for transport errors, 429, 5xx and unreadable bodies (1 s pause, status checked before parsing), and a `agent_wf/<version> (+<contact>)` User-Agent; keep formatting, the 4000-character cut, the no-result message and the `{"error": ...}` mapping in `search_wikipedia`; remove the monkeypatch and any import-time effect; verify `tests/test_wikipedia_tool.py`, using `httpx.MockTransport` and a replaceable sleep, covers every scenario in the `wikipedia-lookup` spec (request parameters, ranking order, disambiguation and empty-page skipping, no result, exact 4000 cut, 300-character query cut, User-Agent contents and the configured contact, retry then success, exactly 3 attempts then an error, no retry for 403/404 with an HTML body never parsed, timeout and unreadable-body errors, unexpected JSON shape, the tool's name, description and argument, and importing the module with the network blocked)
- [x] 2.2 Remove `langchain-community` and `wikipedia` from `pyproject.toml`, add `httpx`, and run `uv lock`; verify `uv sync --locked` passes, `uv tree` shows neither removed package, no import of either remains under `src/` or `tests/`, and a full `uv run pytest -q` no longer prints the langchain-community deprecation warning

## 3. Eval stub and docs

- [x] 3.1 Point the eval Wikipedia stub in `tests/evals/support.py` at `fetch_pages` (returning the fixed Eiffel Tower passage as a `Page`), update `tests/test_eval_support.py` to match (stub removed afterwards, tool returns the fixed text with the network blocked), and update the Evals note in `AGENTS.md` and add a short Wikipedia tool note there (direct API, the `WIKIPEDIA_CONTACT` setting, and a one-line live smoke test to re-run after touching the tool); verify the default suite passes and `uv run pytest -m eval --collect-only -q` still lists 15 cases

## 4. Verification against reality

- [x] 4.1 Run the new tool against the real Wikipedia API for the same three queries; verify that for "Eiffel Tower" (the only query the old tool answered; it returned a 429-caused error for "Mercury" and the nonsense query) the same page titles appear in the same order as the baseline, the format is identical, and summaries match after whitespace normalisation (explain or fix any difference); that "Mercury" skips the disambiguation page and the nonsense query returns the no-result message; that no request gets a 403 or 429; and that latency is recorded next to the baseline
- [x] 4.2 Run `uv run pytest -m eval` once and verify all 15 cases still pass at 3/3 repeats as in the earlier baseline; also ask the real agent, with the real tool and no stub, how tall the Eiffel Tower is, and verify it calls `search_wikipedia` and answers from the result
- [x] 4.3 From a clean copy with no `.env` and no LLM key, verify `uv sync --locked`, `uv run pytest -q` (offline, no langchain-community warning), `uv run ruff check` and `docker build .` all pass, and that the built image contains neither removed package

## Workflow follow-up

- The `langsmith` deprecation warning (Python 3.16) remains; it needs an upstream update, not a change here.
- `examples/AI-Math-Assistant Tool Calling.ipynb` still imports `langchain_community` in its own setup; update it separately if it is meant to keep running.
- If Wikipedia ever starts throttling the default contact URL, set `WIKIPEDIA_CONTACT` to a deployment-specific address (a URL or an email).
- Archive this change after review.
