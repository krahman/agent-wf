# Design

## Context

See proposal.md for motivation and the `agent-evals` spec for required behaviour. What the code looks like today:

- `AGENT_SPECS["math"].build(llm)` returns a runnable agent. `build_llm(model, settings)` creates the `ChatOpenAI` client; it has no temperature option, and raises `RuntimeError("OPENROUTER_API_KEY is not set")` when the key is missing.
- `AgentSpec.build` reads tools from the `TOOLSETS` registry when called, and `search_wikipedia` calls `WikipediaAPIWrapper().run(...)` over the network.
- A run's result is a list of messages: an `AIMessage` carries `tool_calls` (`{"name": "add_numbers", "args": {"numbers": [1, 1]}, "id": ...}`), a `ToolMessage` carries the tool's output, and the last `AIMessage` is the answer. The existing observability code already works from these.
- pytest is configured with `testpaths = ["tests"]` and no markers; CI runs `uv run pytest -q`, which must stay offline. `tests/conftest.py` already exists. PyYAML is installed through langchain.
- Per the project conventions, environment variables are read only in `config.py`. Eval tuning therefore uses pytest command-line options, not new environment variables.

## Goals / Non-Goals

**Goals:**
- One command to run the suite and a clear, comparable result.
- Evals can never run, or spend money, by accident (default run and CI untouched).
- Results that are stable enough to trust: deterministic checks, temperature 0, repeats.

**Non-Goals:**
- An LLM judge, CI integration, multi-turn cases, HTTP-layer cases, Langfuse datasets, or a report-diff tool (see proposal).

## Decisions

**1. Plain pytest with an `eval` marker, not a separate framework or CLI.**
Cases are parametrised tests in `tests/evals/`, marked `eval`. `pyproject.toml` registers the marker and sets `addopts = "-m 'not eval'"`, so `uv run pytest` and CI deselect them; `uv run pytest -m eval` selects only them (a `-m` on the command line overrides the one in `addopts`, which a task verifies). Reuses the existing tooling, selection (`-k`), output and fixtures with no new dependency. Alternatives: a standalone `python -m evals` CLI (nicer summary table, but a second runner to maintain); eval frameworks such as promptfoo, DeepEval or LangSmith evals (new dependency and accounts for a dozen cases); Langfuse datasets (revisit once there are more cases).

**2. Cases live in one YAML file; checks are small pure functions.**
`tests/evals/cases.yaml` is easy to review and extend without touching code. Each case has an `id`, `prompt`, optional `agent` (default `math`) and a `checks` block. Check kinds: `expect_tools`, `forbid_tools`, `tool_args` (a tool name plus the arguments a call must have; listed keys must match, other keys are ignored, numbers compared with a small tolerance, lists element by element), `answer_contains_any`, `answer_contains_all`, `answer_excludes`, `max_tool_calls`. Each check function takes the extracted trace and returns pass or a human-readable failure (expected versus actual). Answer matching is case-insensitive and offers `any` lists because models vary number formatting (`6.25`, `6,25`, `1,000` versus `1000`).

**3. Trace extraction from the agent's messages.**
The harness invokes the real agent once per run (`agent.invoke` with the application's recursion limit), then derives a trace: ordered tool calls (name, args), tool outputs, and the final answer text. Checks only ever see the trace, which is what lets the scoring logic be unit tested with hand-built traces and no model.

**4. Repeats, temperature 0 and a pass-rate threshold.**
`build_llm` gets an optional `temperature` argument (unchanged behaviour when omitted); evals pass 0. Each case runs `--eval-repeats` times (default 3) and passes when its pass rate is at least `--eval-min-pass-rate` (default 1.0). `--eval-model` overrides the model for model comparisons. The options are registered in `tests/conftest.py`, not in `tests/evals/`, because pytest only reads option definitions from conftest files it loads before parsing arguments, and subdirectory conftests are loaded too late. Alternative: environment variables, rejected because settings are read only through `config.py`.

**5. Stub the network call inside the Wikipedia tool, not the tool itself.**
During evals, `WikipediaAPIWrapper.run` is patched to return one fixed passage (the Eiffel Tower's height). The agent still sees the real tool name, description and schema and the real wrapper code runs, so tool selection and use of the result are still tested, while the result no longer depends on Wikipedia. Alternative: swap the `TOOLSETS` entry for a fake tool, which would also stop testing the real tool description.

**6. Report written by a session hook, even for failing runs.**
Each case's per-repeat results go into a session-level collector; a `pytest_sessionfinish` hook writes `tests/evals/results/<UTC timestamp>-<model>.json` with the model, application version, commit, repeats, threshold, per-case pass rate and each failure reason. Only chosen fields are written, never the settings object, so no secrets can end up in it. The folder is gitignored.

**7. Fail before the first case when there is no key.**
A session-scoped fixture in `tests/evals/` checks the configured LLM key and calls `pytest.exit(...)` with a message naming `OPENROUTER_API_KEY`, so a missing key aborts the run with one clear message instead of a failure per case.

## Risks / Trade-offs

- [Real-model results are noisy even at temperature 0] → Repeats plus a configurable threshold; failures list the reason per repeat. The first baseline run decides whether the 100% default is too strict.
- [Some models reject `temperature=0`] → `temperature` is only sent when given; if the default model rejects it, the eval option can drop it. Surfaces immediately on the first run.
- [Number formatting differs between runs or languages, including numbers spelled out as words] → `any` lists in answer checks (for example `2` and `dua`); a failing case shows the answer so the list can be widened.
- [The Wikipedia stub does not test the real tool or the network] → Intended; the real tool keeps its unit tests, and the stub keeps eval results repeatable.
- [Cases tuned to the current prompt stop meaning anything] → Keep cases varied and small in number; review them when the prompt changes.
- [Each run costs money] → Roughly 12 cases x 3 repeats x 2 model calls; `-k` selects a subset and `--eval-repeats 1` cuts it to a third.
- [An eval run is slower than the unit tests] → Acceptable because it is opt-in.

## Migration Plan

Opt-in and additive: nothing changes for the default test run or CI. After merging, run the suite once to record a baseline report and to settle the default repeat count and threshold. Rollback: delete `tests/evals/`, the marker and `addopts` lines, and the `temperature` parameter.

## Open Questions

- Are 3 repeats and a 100% threshold the right defaults? Both are options, so adjusting them after the first baseline run changes neither the specs nor the tasks.
