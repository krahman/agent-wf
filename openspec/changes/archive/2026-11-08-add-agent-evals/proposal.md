# Proposal

## Why

The 62 existing tests use a fake LLM, so they prove the wiring works and nothing about whether the agent behaves well. Changing the system prompt, a tool's description or the model can silently break behaviour such as "satu ditambah satu" becoming `add_numbers([1, 1])`, or an error being reported instead of guessed, and today the only way to find out is to try prompts by hand. This is the next step on the production-readiness list after CI and API hardening, and it is what makes later prompt, model and tool changes safe.

## What Changes

- Add an eval suite that runs a fixed set of cases through the real agent against a real model and checks, with plain assertions, which tools were called with which arguments and what the final answer says.
- Keep it entirely outside the normal test run and CI: evals run only on request with `uv run pytest -m eval`, so `uv run pytest` and the CI pipeline stay offline, free and unchanged.
- Run each case several times at temperature 0 and judge it on a pass rate, so real-model noise does not cause false alarms; the repeat count, pass-rate threshold and model are command-line options.
- Replace the Wikipedia tool with a fixed stub during evals, so results depend on the agent and not on Wikipedia being reachable.
- Write a JSON report per run (model, version, commit, per-case results) so two runs can be compared after a change.
- Seed the suite with about a dozen cases covering each math tool, argument order, multi-step arithmetic, non-English prompts, number formats, divide-by-zero error reporting and refusing to guess when a tool is available.
- Document how to run and extend the suite in `AGENTS.md`.

Out of scope, with the reason:
- Running evals in CI (cost and flakiness; a deliberate choice to keep them local for now).
- An LLM judge for free-text quality: checks are deterministic, which is cheaper and repeatable. Revisit if wording quality becomes the thing to measure.
- Multi-turn and thread-memory cases, and testing through the HTTP layer (auth, limits and errors already have their own tests).
- Langfuse datasets or score upload, and a tool to diff two reports.

## Capabilities

### New Capabilities
- `agent-evals`: how the agent's real-model behaviour is checked on demand: what a case asserts, how runs are repeated and scored, how they stay isolated from CI and from network tools, and what each run reports.

### Modified Capabilities

None. The existing specs (`continuous-integration`, `api-access-control`, `request-limits`, `failure-handling`, `service-runtime`) are unaffected: the default test run and CI behave exactly as before.

## Impact

- New code under `tests/evals/`: a case file, the harness (trace extraction and checks) and the pytest runner; unit tests for the harness in the default suite (no LLM).
- `pyproject.toml`: register the `eval` marker, exclude it by default, and list `pyyaml` explicitly in the dev group (it is already installed through langchain); `uv.lock` updates accordingly.
- `src/agent_wf/llm.py`: `build_llm` gains an optional `temperature` argument; no behaviour change when it is omitted.
- `.gitignore` for the report folder; `AGENTS.md` gains an Evals section.
- Running the suite needs `OPENROUTER_API_KEY` and costs a small amount per run (roughly 12 cases x 3 repeats x 2 model calls).
- CI is unaffected: the default `uv run pytest` deselects evals, and the lint job also checks the new files.
