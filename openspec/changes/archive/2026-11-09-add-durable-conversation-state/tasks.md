# Tasks

## 1. Dependencies and settings

- [x] 1.1 Add `langgraph-checkpoint-postgres` and `psycopg[binary,pool]` to `pyproject.toml`, run `make lock`, confirm `make install` and the unit tests still pass
- [x] 1.2 Add `database_url` (SecretStr), `state_pool_size` (5), `state_retention_days` (30) to `Settings` in `config.py`; unit tests for defaults and for the URL never appearing in `repr` or logs
- [x] 1.3 Add the three settings to `.env.example` with comments (what the URL looks like, pool-size vs `max_connections` rule)

## 2. State package

- [x] 2.1 Create `src/agent_wf/state/` with a pool + checkpointer factory (Postgres when `DATABASE_URL` is set, `InMemorySaver` plus a startup warning otherwise); no work at import time
- [x] 2.2 Implement `migrate` (`setup()` with retry on `UniqueViolation`) and the schema check used at startup (latest `checkpoint_migrations` version present, otherwise an error that says to run the migration); `python -m agent_wf.state migrate`
- [x] 2.3 Implement the per-thread lock: advisory try-lock with a stable 64-bit hash on a dedicated pooled connection, released in `finally`; per-process `asyncio.Lock` registry in memory mode; raises `ApiError(409, "thread_busy", ...)`
- [x] 2.4 Implement the repair of dangling tool calls (error `ToolMessage` per unanswered call via `aupdate_state`), untouched when the history is healthy
- [x] 2.5 Implement prune: `prune_thread` (keep latest checkpoint, best effort) and `prune_idle` (threads idle longer than retention, newest checkpoint age from the checkpoint ID); `python -m agent_wf.state prune` prints the number of threads deleted

## 3. API

- [x] 3.1 In `lifespan`, build the pool and checkpointer, run the startup schema check, build agents with the checkpointer plus one checkpointer-less copy per spec, close the pool after `yield` (and keep `shutdown_tracing()`)
- [x] 3.2 In the agent endpoint: no `thread_id` means the stateless agent and no thread in `request.state` or logs; with one, take the lock, repair, run, prune in `finally`, release the lock
- [x] 3.3 Add `thread_busy` (409) and map state-access failures (psycopg operational errors, pool timeout) to `ApiError(503, "state_unavailable", ...)` with the detail only in the server log; confirm an LLM failure is still 502 and a run timeout still 504
- [x] 3.4 Extend `check_startup` for the configured-but-unreachable and not-migrated cases (errors never contain the password)

## 4. Compose, Makefile and CI

- [x] 4.1 Add `app-db` (postgres:17, own volume, healthcheck) and `db-migrate` (one-shot, API image) to `docker-compose.yml`; `api` depends on `db-migrate` with `service_completed_successfully`; set `DATABASE_URL` for `api` and `db-migrate`; pass `docker compose config -q`
- [x] 4.2 Add `make migrate` and `make prune` (run against the compose stack), keep `make reset` deleting the new volume, update the `.PHONY` and help text; extend `tests/test_makefile.py` accordingly
- [x] 4.3 Add a `postgres:17` service and `TEST_DATABASE_URL` to the CI `test` job; keep `make check` and the CI workflow in step (the Makefile test fails otherwise)

## 5. Tests

- [x] 5.1 Unit tests (no database): no-thread requests are stateless and need no database; 409 mapping; 503 mapping without detail; repair on a fake history with and without dangling calls; in-memory fallback warning; startup errors
- [x] 5.2 Database tests under `tests/db/` (marker `db`, skipped without `TEST_DATABASE_URL`): continue after pool/saver recreation, 8 concurrent migrations, lock refuses the second run and releases after cancel, repair after a cancelled tool call, prune keeps messages, idle deletion past and within retention, checkpoint-ID age assumption
- [x] 5.3 Add a cancelled-tool-call case to the real-model checks only if a cheap way exists; otherwise record in the test file why it is covered offline (it was confirmed once against the real model: HTTP 400 without the repair)

## 6. Docs and verification

- [x] 6.1 Update `AGENTS.md`: state section (when state is kept, retention, lock, repair, migrate/prune), errors table (`thread_busy`, `state_unavailable`), limits (thread ID optional means stateless), commands table, container section
- [x] 6.2 Verify end to end on the compose stack: `make up`, a conversation continued after `docker compose restart api`, two parallel requests on one thread (one 409), a poisoned thread repaired, `make prune`, `make migrate` twice; run `make check`; `make spec-check`
- [x] 6.3 Update the roadmap memory (durable state done, eval dataset next)
