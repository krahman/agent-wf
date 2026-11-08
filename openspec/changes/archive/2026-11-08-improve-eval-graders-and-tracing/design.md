# Design

## Context

See proposal.md for motivation and the delta for `agent-evals` for the new requirements. Current state, verified in the code:

- `tests/evals/harness.py` runs checks against a trace. `answer_contains_any`, `answer_contains_all` and `answer_excludes` use case-insensitive **substring** matching, and `tool_args` compares argument lists **in order**. Demonstrated: for the case expecting `2`, the answers "dua belas", "12" and "20" all pass; `multiply_numbers([7, 6])` fails a case expecting `[6, 7]`.
- 13 of the 15 seed cases check a number in the answer with `answer_contains_any` (listing format variants by hand); the two divide-by-zero cases check words, not numbers.
- `run_case_once(case, agent, recursion_limit)` calls `agent.invoke(...)` with only a recursion limit: no callbacks, no tracing. The API attaches Langfuse through `configure_tracing` (needs `Settings.langfuse_tracing` true), `trace_callbacks()` (empty unless configured) and `shutdown_tracing()` (flush); none of that runs in a pytest process.
- The report (`tests/evals/report.py`) is written by a session hook; `started_at` is taken when the report is built, and the file name derives from it.
- Langfuse SDK 5.2.0 provides: `create_score(name, value, trace_id, data_type="BOOLEAN", comment=...)`, `CallbackHandler.last_trace_id`, `propagate_attributes(trace_name, session_id, tags, metadata)` and `flush()`.
- Project convention: only `config.py` reads environment variables; eval tuning is by pytest options registered in `tests/conftest.py`.

## Goals / Non-Goals

**Goals:**
- Graders that reject wrong answers and accept right ones, with the cases staying readable.
- Eval failures that can be opened in Langfuse, without making Langfuse a requirement for evals.

**Non-Goals:**
- Latency and token reporting, new and harder cases, LLM judges, Langfuse datasets or experiments, any change to application code (see proposal).

## Decisions

**1. A numeric check that compares values: `answer_number`.**
A case lists `answer_number` entries, each `{value: <number>, words: [<optional whole words>]}`; every entry must be satisfied. The check finds numeric tokens in the answer and passes if any token's value equals `value` (relative tolerance 1e-9). Token rules, prototyped against 49 accept and reject assertions before this design was written:
- A token is an optional sign (`-` or the Unicode minus) followed by digits, optionally grouped with `,`, `.` or a space (thousands) and optionally ending in a decimal part. A token must not touch a word character or continue as `.digit`/`,digit`, so the 2 inside `12`, `20`, `2nd` or `1.0.0` is never a match, and a trailing full stop (`42.`) is not part of the number.
- A separator is ambiguous, so a token yields every well-formed reading: grouping needs groups of exactly three digits after a first group of one to three (`3.500` is 3500 or 3.5; `1,024` is 1024 or 1.024), a decimal mark must be last (`6,25` and `6.25` are 6.25; `4.2` is 4.2 only, not 42; `6,25` is not 625).
Alternatives: keep substrings and list every variant by hand (what is wrong today); regular expressions written in the YAML (powerful but unreadable and easy to get wrong); only look at the last number in the answer (stricter, but correct answers often end with a unit or a second figure such as "330 metres (1,083 ft)").
Known limit: the check proves the answer *states* the number somewhere, not that it is the final result ("2 and 5 make 7" satisfies an expected 2). Acceptable here because the tool and its arguments are checked separately; revisit if it bites.

**2. Spelled-out numbers are whole-word alternatives; compounds are ruled out by `answer_excludes`.**
`words` entries match case-insensitively as whole words ("dua" does not match inside "duapuluh"). "dua belas" (12) still contains the whole word "dua", so the two Indonesian cases pair `words: [dua]` with `answer_excludes: [belas, puluh, ratus, ribu]`. Language-specific rules therefore live in the case file, not in the harness. Alternative: a built-in spelled-number parser per language (large, and wrong as soon as another language appears).

**3. `unordered: true` on a `tool_args` entry, explicit per case.**
Lists of numbers are then compared as multisets; default stays ordered so `subtract_numbers([3, 10])` against `[10, 3]` still fails. Alternative: have the harness know that `add_numbers` and `multiply_numbers` are commutative (less YAML, but a hidden rule inside a generic harness that must stay correct for tools added later).

**4. Move the 13 numeric cases to `answer_number` and mark commutative argument checks unordered.**
`answer_contains_*` stays for phrase checks (the divide-by-zero cases). The existing `test_eval_suite` coverage tests keep guarding the case file, and new unit tests replay the demonstrated wrong answers ("dua belas", "12", "20") and the swapped-order run as regression tests.

**5. `--eval-trace` forces tracing on for the session, reusing the application's seam.**
The option is registered in `tests/conftest.py` with the others. A session fixture (only active with the flag) builds `get_settings().model_copy(update={"langfuse_tracing": True})` and calls `configure_tracing` on it, so the flag works even when `LANGFUSE_TRACING=false` in `.env` and no application code changes. Before any model call it checks (a) the public and secret keys exist and (b) `GET <host>/api/public/health` answers within 3 s, and otherwise exits with an error naming the missing setting or the unreachable address. Alternative: trace automatically whenever keys are present (rejected: a normal eval would need the Langfuse stack and would add traffic unasked).

**6. One trace and one score per repeat; traces through the SDK, scores through Langfuse's REST API.**
`tests/evals/tracing.py` wraps each repeat. For the trace: `trace_callbacks()` supplies the handler (so `last_trace_id` is available) and `propagate_attributes(trace_name="eval:<case-id>", session_id=<run id>, tags=[eval, case:<id>, repeat:<n>, model:<model>])` names and groups it. For the score: after the repeat, a `POST <host>/api/public/scores` with `{name: "eval_pass", value: 1 or 0, dataType: "BOOLEAN", traceId, comment: <failure reasons>}`, authenticated with the Langfuse keys. `shutdown_tracing()` flushes the traces when the session ends. The run id is the report's file stem (`<UTC timestamp>-<model>`), computed once at session start and used for both, so a report maps to exactly one Langfuse session.
**Why not the SDK's `create_score`:** found by the first real traced run, not by the unit tests. SDK 5.2.0 sends scores in a batch that the self-hosted server this project runs (3.227.0) rejects with HTTP 400 ("expected object, received array" in the server log), so no score ever arrived, while traces were fine. The plain REST endpoint is accepted, was verified to store a boolean score with its comment, and returns a status the tracer can check. It is also synchronous, so the tracer stops attempting scores after the first failure: an outage then costs one 3 s timeout, not one per repeat.
Alternatives: extend `trace_context` in the application to take tags and metadata (spreads eval concerns into application code); upgrade the Langfuse server image to match the SDK (a stack change beyond this change; the REST call works on both).

**7. Tracing and scoring can never change a result.**
Every Langfuse call in the helper is wrapped so an exception is logged and swallowed; the SDK sends in the background, so an outage after the preflight neither fails nor slows cases. A case passes or fails on its checks alone.

**8. The report gains trace links only for traced runs.**
A traced report adds `langfuse: {host, session_id}`, and for each case the list of its repeats' trace IDs; each failure entry also carries its `trace_id`. An untraced report is byte-for-byte what it is today (a test asserts there are no trace fields).

## Risks / Trade-offs

- [Ambiguous separators accept both readings, so `3.500` satisfies an expected 3.5 as well as 3500] → Only well-formed readings are produced and partial matches are impossible; the leniency is confined to the genuinely ambiguous token, and the demonstrated false positives are gone.
- [The number check proves the answer mentions the number, not that it is the final answer] → Documented limit; tool and argument checks cover correctness of the computation.
- [A traced run adds 45 traces and 45 scores to the Langfuse project, next to real API traces] → Every one is tagged `eval` and shares a session per run, so they can be filtered or deleted as a group.
- [The SDK and the self-hosted server disagree on the score format (observed: HTTP 400)] → Scores use the REST endpoint instead, verified against the real server. A future Langfuse upgrade could change the endpoint; the real traced run in the tasks would catch it, and the failure is logged and never affects a result.
- [Scores are ingested asynchronously (about 8 s) and may arrive before their trace is visible] → Langfuse joins them by trace id; the real run checks all 45 end up attached.
- [A mid-run Langfuse outage silently drops traces] → Intended trade-off (evals must not depend on it); the SDK logs the failure, and the report would list trace IDs that Langfuse never received, which is visible when opened.
- [`--eval-trace` overrides `LANGFUSE_TRACING=false`] → That is the point of an explicit flag; documented.
- [Trace and report session ids derive from a timestamp in seconds] → Two runs started in the same second with the same model would share an id; negligible for a hand-run command.

## Migration Plan

Additive and test-only. The default `make eval` and `uv run pytest` behave as before except for the corrected graders, so one full eval run on the real model confirms the suite still passes at 3/3 before tracing is tried. Rollback is a revert; no data or application code is involved.

## Open Questions

None that would change the specs, the approach or the tasks.
