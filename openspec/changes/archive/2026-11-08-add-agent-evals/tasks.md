# Tasks

## 1. Harness core (no model needed)

- [x] 1.1 Add an optional `temperature` argument to `build_llm` in `src/agent_wf/llm.py`, sent to the client only when given; verify a unit test shows the client's temperature is unset by default and `0` when passed
- [x] 1.2 Create `tests/evals/harness.py` with trace extraction (ordered tool calls with name and args, tool outputs, final answer text) from a list of agent messages, and the check functions `expect_tools`, `forbid_tools`, `tool_args` (partial match, numeric tolerance, lists element by element), `answer_contains_any`, `answer_contains_all`, `answer_excludes` (case-insensitive) and `max_tool_calls`, each returning pass or an expected-versus-actual message; verify `tests/test_eval_harness.py` builds messages by hand and covers every check passing and failing, including the `[3, 10]` versus `[10, 3]` argument-order failure message
- [x] 1.3 Add case loading with validation (`id`, `prompt`, optional `agent` defaulting to `math`, `tags`, a `checks` block; reject unknown check names, duplicate IDs and missing fields) and add `pyyaml` to the dev group in `pyproject.toml`; verify loader tests for each rejection, `uv lock` updates `uv.lock`, and `uv sync --locked` passes

## 2. Scoring and report

- [x] 2.1 Add case scoring: given the results of N repeats and a minimum pass rate, return the pass rate, pass or fail, and the failure reason of each failed repeat; verify tests for 3 of 3 (passes), 2 of 3 at 100% (fails with the failing repeat's reason) and 2 of 3 at 60% (passes)
- [x] 2.2 Add the report builder and writer producing `<UTC timestamp>-<model>.json` with model, application version, commit, repeats, threshold, time, and per-case pass rate and failure reasons, written for passing and failing runs and containing only chosen fields; verify tests with `tmp_path` for a passing and a failing run, and that a fake API key placed in the settings does not appear in the file

## 3. Pytest wiring

- [x] 3.1 Register the `eval` marker and set `addopts = "-m 'not eval'"` in `pyproject.toml`; add `--eval-repeats` (default 3), `--eval-min-pass-rate` (default 1.0) and `--eval-model` to `tests/conftest.py`; verify `uv run pytest --collect-only -q` lists no eval case, `uv run pytest -m eval --collect-only -q` lists only eval cases (so the command-line `-m` overrides `addopts`), and `uv run pytest --help` shows the three options
- [x] 3.2 Add the runner `tests/evals/test_agent_evals.py` (module marked `eval`): one test per case that builds the agent with `build_llm(model, temperature=0)`, runs it the requested number of times, scores it and fails with the per-repeat reasons; add a session fixture that calls `pytest.exit` naming `OPENROUTER_API_KEY` when the key is missing, and a fixture that patches `WikipediaAPIWrapper.run` to return one fixed passage; verify default-run tests show the key-missing fixture exits with a message naming the setting but not a value, and that the lookup tool returns the fixed passage with the network call patched out
- [x] 3.3 Write the report from a `pytest_sessionfinish` hook (only when eval cases ran, also when some failed) and add `tests/evals/results/` to `.gitignore`; verify a unit test that drives the hook with a fake collector writes the file, and `git check-ignore tests/evals/results/x.json` succeeds

## 4. Seed cases

- [x] 4.1 Write `tests/evals/cases.yaml` with at least 12 tagged cases: add, subtract and divide with argument order, multiply, power, a multi-step calculation, the Indonesian "satu ditambah satu", thousands separators, negative numbers, divide by zero reporting the error without a number, a large calculation that must use a tool rather than a guess, and a lookup-plus-calculation case that uses the Wikipedia stub; verify tests that all cases load and validate, IDs are unique, and every category named in the spec is covered by a tag

## 5. Documentation and real-model run

- [x] 5.1 Add an Evals section to `AGENTS.md`: how to run (`uv run pytest -m eval`, `-k` to select, the three options), the case format and how to add a case, that the Wikipedia tool is stubbed, where reports go, and the cost; verify each command shown runs as written (collection form for those that need no key)
- [x] 5.2 Run `uv run pytest -m eval` against the configured model twice; verify a report file exists after each run with the required fields, the per-case pass or fail is the same in both runs, and any case that fails is checked against the agent's real behaviour (fix a wrong expectation, never loosen a check to hide a real defect), then record the baseline pass rates in the final summary
- [x] 5.3 Verify the default run is unchanged and offline: from a clean copy with no LLM key, `uv sync --locked`, `uv run pytest -q` (evals reported as deselected, none run), `uv run ruff check` (covers the new files) and `docker build .` all pass

## Workflow follow-up

- Decide whether 3 repeats and a 100% threshold are right once the baseline is known, and adjust the defaults if needed.
- Add a case whenever a prompt, tool or model change causes a regression that the suite did not catch.
- Later candidates, deliberately out of scope here: a manually triggered CI job for the evals, Langfuse datasets, and a report-diff tool.
- Archive this change after review.
