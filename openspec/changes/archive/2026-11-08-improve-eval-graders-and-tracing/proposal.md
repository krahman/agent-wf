# Proposal

## Why

A review of the eval suite found two things that stop it from being trustworthy and debuggable:

- **The graders are wrong in both directions.** Answers are checked by substring, so a wrong answer passes: for the case expecting `2`, the answers "dua belas" (12), "12" and "20" all pass. Argument checks are order-strict, so a correct run is rejected: `multiply_numbers([7, 6])` fails a case expecting `[6, 7]`, although multiplication is commutative and the answer is right. A suite that can pass a wrong answer and fail a right one can't be relied on to guard changes.
- **Failures cannot be investigated.** Eval runs are never traced, because Langfuse tracing is wired into the API only. When a case fails, all you get is a one-line check message, not what the model saw, what it called, or why.

## What Changes

- Add a numeric answer check that compares numbers as numbers, not as text: `2` no longer matches inside `12` or `20`, and `3500`, `3,500`, `3.500` and `3 500` (and `6,25` and `6.25`) are recognised as the same value. Spelled-out forms (such as "dua") can be listed per case as whole-word alternatives, with the existing excludes ruling out compounds like "dua belas".
- Add an opt-in `unordered` flag on argument checks, used for commutative operations (add, multiply), so a correct run with its numbers in another order is no longer rejected. Order stays strict by default, so a subtraction with swapped numbers still fails.
- Move the seed cases to the new checks and keep the suite passing at 3/3 on the real model.
- Add an opt-in `--eval-trace` option. With it, every eval repeat is traced to Langfuse as `eval:<case-id>`, grouped into one session per run, and tagged with the case, repeat and model. Without it nothing changes: a normal `make eval` stays fully local and needs no Langfuse.
- Record each traced repeat's result in Langfuse as a boolean `eval_pass` score, with the failure reasons as its comment, so failing runs are visible and filterable there.
- Fail fast and clearly when `--eval-trace` is requested but Langfuse is not configured or not reachable, before any model call is made.
- Add the trace IDs, the session and the Langfuse host to the JSON report, so a failing case links straight to its trace.
- Document the new checks and the option in `AGENTS.md`.

Out of scope, with the reason:
- Per-case latency, token and cost numbers, more and harder cases, negative and adversarial cases, and building cases from real traffic: separate steps that this change makes easier but does not do.
- An LLM judge or Langfuse-hosted evaluators, datasets and experiments: no concrete failure mode needs them yet.
- Changing the agent or the API; this change touches only the eval suite and its tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `agent-evals`: adds requirements for numeric answer checks, order-independent argument checks, opt-in tracing and scoring in Langfuse, clear failure when tracing cannot start, and reports that link to their traces. Existing requirements are unchanged.

## Impact

- Code (tests only): `tests/evals/harness.py` (new check and flag), `tests/evals/cases.py` and `cases.yaml` (new check kinds, updated seed cases), `tests/evals/support.py` and `tests/evals/conftest.py` (tracing and scoring), `tests/evals/report.py` (trace links), a new `tests/evals/tracing.py`, and `tests/conftest.py` (the new option); matching unit tests. No application code changes: tracing reuses `configure_tracing`, `trace_callbacks` and `shutdown_tracing` from `agent_wf.observability`.
- Docs: the Evals section of `AGENTS.md`.
- Behaviour: a normal `make eval` or `uv run pytest` is unchanged; CI is unaffected. A traced run (`make eval ARGS=--eval-trace`) needs the Langfuse stack up and its keys in `.env`, and adds one trace and one score per repeat (45 for a default run of 15 cases) to the Langfuse project.
- Observed while planning and implementing: the installed Langfuse SDK (5.2.0) provides trace IDs from the callback handler, tags, sessions and a flush, so tracing needs no new dependency. Its score call is rejected by the self-hosted server (HTTP 400, found by the first real traced run), so scores are sent through Langfuse's REST API instead.
