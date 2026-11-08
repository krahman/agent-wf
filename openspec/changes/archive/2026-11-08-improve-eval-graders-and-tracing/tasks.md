# Tasks

## 1. Graders

- [x] 1.1 Add the `answer_number` check: a `{value, words}` entry model on `Checks`, number extraction with the token and reading rules from design decision 1 in a new `tests/evals/numbers.py`, integration in `run_checks` with a failure message that shows the expected value and the numbers the answer does state, and `Checks.is_empty` counting it; verify `tests/test_eval_numbers.py` covers accept and reject lists (accept: `3500` as `3,500` / `3.500` / `3 500` / `3500`, `6.25` as `6,25`, `1024` in all four grouped forms, `-2` with ASCII and Unicode minus, a number inside a sentence or next to a unit and a trailing full stop; reject: 2 in `12`, `20`, `22`, `2nd`, `page 12 of 20`, 42 in `142` and `4.2`, 625 in `6,25`, 35 in `3.5`, 1 in `1.0.0`), whole-word `words` alternatives ("dua" matches "dua", not "duapuluh"), and that every entry in a list must be satisfied
- [x] 1.2 Add the `unordered` flag to `tool_args` entries (multiset comparison of list arguments, ordered by default); verify tests that `[7, 6]` satisfies an unordered `[6, 7]`, a swapped subtraction still fails when ordered, `[6, 8]` fails even when unordered, duplicates are counted (`[6, 6, 7]` against `[6, 7, 6]` passes, against `[6, 7]` fails), and non-list arguments are unaffected
- [x] 1.3 Move the 13 numeric seed cases in `cases.yaml` from `answer_contains_any` to `answer_number` (with `words` and `answer_excludes` for the two Indonesian cases and the negative-number case) and mark the add and multiply argument checks `unordered`; verify the existing loader and coverage tests pass, and that regression tests replay the demonstrated wrong answers ("dua belas", "12", "20" for `add-indonesian`) and a swapped `[7, 6]` for `multiply-basic` through the shipped cases and get reject, reject, reject and accept

## 2. Opt-in tracing

- [x] 2.1 Register `--eval-trace` in `tests/conftest.py`; compute the run's start time once at session start and use it for the report name and the session id; add a session fixture, active only with the flag, that forces tracing on through `configure_tracing(get_settings().model_copy(update={"langfuse_tracing": True}))` after checking that both Langfuse keys are set and that `GET <host>/api/public/health` answers within 3 s, exiting with a message that names the missing setting or the unreachable address and never a secret; verify unit tests with fake settings and a patched HTTP client for missing keys, an unreachable host, and that without the flag nothing is configured and no request is made
- [x] 2.2 Add `tests/evals/tracing.py` and wire it into `run_case_once` and the runner: per repeat, a handler from `trace_callbacks()`, `propagate_attributes` with trace name `eval:<case-id>`, the run's session id, tags `eval`, `case:<id>`, `repeat:<n>`, `model:<model>`, then a boolean `eval_pass` score on the repeat's trace with the failure reasons as the comment, all wrapped so any Langfuse error is logged and never changes a result, and a flush when the session ends; verify unit tests with a fake Langfuse client and handler for the trace name, session, tags, the score's value, type and comment for a passing and a failing repeat, that a raising client does not change pass or fail, and that an untraced run makes no Langfuse call
- [x] 2.3 Add trace links to the report for traced runs only (`langfuse` with host and session id, each case's repeat trace IDs, and the `trace_id` in each failure entry); verify unit tests that a traced report contains them and an untraced report has no trace, session or host fields

## 3. Documentation

- [x] 3.1 Update the Evals section of `AGENTS.md`: `answer_number` (with `words` and the excludes pattern), `unordered`, `--eval-trace` (opt-in, needs Langfuse up and its keys, works with `LANGFUSE_TRACING=false`), the `eval_pass` score and the report's trace fields; verify the documented example check blocks load through the case loader, `uv run pytest --help` shows `--eval-trace`, and `make eval-list` still runs as documented

## 4. Verification against the real system

- [x] 4.1 Run the full eval suite without the flag on the real model; verify all 15 cases pass at 3/3 with the new graders (a failing case is checked against the agent's real behaviour: fix a wrong expectation, never loosen a check to hide a defect), and that the Langfuse project's trace count did not change
- [x] 4.2 Run `make eval ARGS=--eval-trace` against the running Langfuse; verify through Langfuse's API that the run created 45 traces named `eval:<case-id>` in one session whose id equals the report's file stem, carrying the expected tags, with 45 `eval_pass` scores of boolean type, all true, and that the trace IDs in the report resolve
- [x] 4.3 Prove the failure path for real: temporarily make one case's expected number wrong (reverted afterwards) and run that case traced with one repeat; verify pytest fails, its trace carries an `eval_pass` score of false with the failed check in the comment, and the report's failure entry has a `trace_id` that resolves; also verify `--eval-trace` with `LANGFUSE_HOST` pointing at an unreachable address stops before any model call and names that address
- [x] 4.4 From a clean copy with no `.env` and no key, verify `uv sync --locked`, `uv run pytest -q` (offline, evals deselected), `uv run ruff check` and `make check` all pass

## Workflow follow-up

- Add per-case latency and token counts to the report, and more, harder and negative cases built from reviewing real traces: the loop this change makes possible.
- Tagged eval traces can be filtered or deleted as a group in Langfuse if they become noise.
- Add a narrow LLM judge or Langfuse-hosted evaluator only when a concrete quality problem needs it.
- Archive this change after review.
