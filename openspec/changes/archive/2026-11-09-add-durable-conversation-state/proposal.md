# Proposal

## Why

Conversation state lives in one `InMemorySaver` per process: it is lost on every restart, cannot be shared by several API instances, and only grows. Measured on the current code: every request without a `thread_id` stores a thread the caller can never reach (200 calls left 200 threads), a 60-turn conversation stores 723 times what its first turn took, and a run cancelled by the time budget leaves a tool call without a result that makes every later request on that thread fail upstream (HTTP 400 from the model, reported as 502). Moving to a database without fixing these would make them permanent, and the goal is to run several instances, so state has to be shared and safe before that.

## What Changes

- Persist conversation state in PostgreSQL through LangGraph's async Postgres checkpointer, shared by all instances and agents. A separate app database (own container and volume in compose), not Langfuse's.
- Persist only requests that carry a `thread_id`. A request without one runs without saved state (stateless), so it leaves nothing behind and does not depend on the database.
- **BREAKING (internal contract):** a request without `thread_id` no longer runs under a generated, stored ID; the generated ID was never returned to callers, so no caller could have continued it.
- Repair a thread before each run: an assistant tool call with no tool result (left by a cancelled or crashed run) is closed with an error result, so the thread keeps working.
- Refuse a second simultaneous request on the same thread with 409 `thread_busy` (per-thread lock), instead of silently losing one of them.
- Keep only the latest checkpoint of a thread after each run (prune), to stop growth faster than conversation length.
- Delete threads idle longer than a configurable retention (default 30 days) with a prune command meant to run on a schedule, once, outside the API instances.
- Run database migrations as a one-shot step before the instances start; instances check that the schema exists and refuse to start otherwise. Instances never run migrations concurrently.
- Report an unreachable state database as 503 `state_unavailable` for requests that carry a `thread_id`; fail startup when a database is configured but unreachable.
- Without `DATABASE_URL` the service keeps using in-memory state and logs a warning (local development), same opt-out style as `API_AUTH_ENABLED`.
- Bound each instance's connection pool by a setting so instances times pool size fits the database's connection limit.

## Capabilities

### New Capabilities
- `conversation-state`: how conversations are stored and continued: persistence only for requests with a thread ID, shared across instances, repair of interrupted runs, one run per thread at a time, pruning and retention, migrations, and behaviour when the database is unavailable.

### Modified Capabilities
- `request-limits`: a request without a `thread_id` is processed without saved state instead of under a generated ID.
- `failure-handling`: two new stable error codes, `thread_busy` (409) and `state_unavailable` (503).
- `service-runtime`: startup requires a reachable, migrated state database when one is configured, and the compose stack gains the database and the one-shot migration step.
- `developer-commands`: targets to migrate the state database and to prune old conversations; `make reset` also removes the conversation data.
- `continuous-integration`: the test job provides a Postgres service so the real-database tests run in CI.

## Impact

- Code: `api/app.py` (lifespan builds pool and saver, endpoint locks and repairs), new `src/agent_wf/state/` package (pool, saver factory, migrate, lock, repair, prune), `config.py` (`DATABASE_URL`, pool size, retention), `api/errors.py`, `api/startup.py`, `agents/spec.py` unchanged.
- Dependencies: `langgraph-checkpoint-postgres`, `psycopg[binary,pool]` (about 39 packages in a dry run); `uv.lock` changes.
- Infrastructure: new `app-db` Postgres service and volume, `db-migrate` one-shot service, `api` depends on both; `.env.example` gains the new settings.
- Tests: unit tests keep a fake or in-memory saver and need no database; a small set of real-Postgres tests, skipped when no database is configured and run in CI against a service container.
- Docs: AGENTS.md sections for state, errors table, limits and commands.
- Out of scope: a `DELETE /threads/{id}` endpoint, thread ownership or per-user isolation (callers are internal), conversation summarising or trimming, and the evaluation dataset work (next roadmap item).
