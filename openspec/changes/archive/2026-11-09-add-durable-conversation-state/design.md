# Design

## Context

State today: `api/app.py` builds one `InMemorySaver` in `lifespan` and passes it to every `AgentSpec.build(llm, checkpointer)`. The endpoint uses `body.thread_id or uuid4()`, runs `agent.ainvoke` inside `asyncio.timeout`, and never returns a generated ID. The image runs one uvicorn worker; the goal of this change is several instances (and workers) sharing state. See proposal.md for the measured problems.

Facts measured in a spike against a real Postgres 17 (langgraph 1.2.20, `langgraph-checkpoint-postgres` 3.2.0, `psycopg` 3.3):
- `setup()` run by 8 instances at once: 1 succeeded, 7 crashed with `UniqueViolation` (the database ended up fully migrated anyway). Retrying `setup()` made all 8 succeed. A lock held on a connection while `setup()` ran hung in one variant, so locks around `setup()` are not used.
- A run cancelled by the time budget leaves state `[Human, AI(tool_calls)]` with `next=('tools',)`; it survives a restart. `durability="exit"` did not prevent it.
- 60 turns in one thread: 180 checkpoint rows (about 0.9 MB). `aprune(["t"], strategy="keep_latest")` left 1 row, the messages stayed intact and the thread continued.
- Two simultaneous runs on one thread: no error, one human message silently lost. A per-thread Postgres advisory try-lock refused the second run and a retry succeeded.
- Postgres defaults to 100 connections; each instance holds its own pool.

## Goals / Non-Goals

**Goals:**
- State shared by all instances, surviving restarts; no unreachable, unbounded or poisoned threads.
- Offline unit tests and local development keep working with no database.

**Non-Goals:**
- Thread ownership or per-user isolation (callers are internal); a delete-thread endpoint; trimming or summarising long histories; sharding or replicas of the database; a scheduler (the prune command is run by whatever scheduler the deployment has).

## Decisions

**1. Postgres through `AsyncPostgresSaver` on an `AsyncConnectionPool`.** Built in `lifespan`, closed after `yield`. Alternative: SQLite on a volume, simpler but one writer, so no several instances (the stated goal). Pool settings follow the spike: `autocommit=True`, `prepare_threshold=0`, `row_factory=dict_row`.

**2. A separate app database, not Langfuse's.** New compose service `app-db` (`postgres:17`, own volume, credentials from `.env` with local-dev defaults like the existing ones). Langfuse's Postgres has its own migrations, upgrades and connection budget, and `make reset` of one should be a conscious choice for the other. In production `DATABASE_URL` points at a managed Postgres.

**3. Two checkpointers by configuration, one code path.** `DATABASE_URL` set: Postgres saver. Unset: `InMemorySaver` and a startup warning (like `API_AUTH_ENABLED=false`). The thread lock and the repair are written against the checkpointer interface (`aget_state`/`aupdate_state`), so they work with both; only the lock needs the database (see 5) and is a per-process `asyncio.Lock` per thread in memory mode.

**4. Stateless when there is no `thread_id`.** The endpoint builds the config without `thread_id`-keyed state: a second, checkpointer-less agent per spec is built at startup (`spec.build(llm, None)`), and requests without `thread_id` use it. This removes the leak at its root, needs no database for such calls and avoids writing and then deleting. Alternative: persist and delete after the run; rejected, it costs writes and still leaks when a run dies. `request.state.thread_id` and the log/trace thread ID stay unset for these requests (as for a missing ID today they were a random value; logs show `-`).

**5. Per-thread lock with a Postgres advisory lock, one dedicated connection per run.** `pg_try_advisory_lock(hash(thread_id))` on a connection taken from the pool and held for the whole run, released in `finally`; a busy lock gives `ApiError(409, "thread_busy")`. Session-level locks are freed by Postgres if the instance dies. The hash is a stable 64-bit value of the thread ID (not Python's `hash`, which is per process). Costs one pooled connection per in-flight conversation run, so pool size bounds concurrent conversation runs; a request that cannot get a connection within a short wait is a `state_unavailable`. Alternative: row lock in a table, which needs a schema of our own; rejected for now.

**6. Repair before each run.** Read the thread state; for each `AIMessage` whose tool call IDs have no following `ToolMessage`, add a `ToolMessage(status="error", content="The tool call was interrupted before it finished")` through `aupdate_state(..., as_node="tools")`, then run. It happens under the lock, only when needed (a healthy thread is not written). Alternative: roll back to the last good checkpoint; rejected, it discards the user's message and is harder to explain in the history.

**7. Prune after each run, and idle-thread deletion as a command.** After a run on a thread (in `finally`, best effort, errors only logged): `aprune([thread_id], strategy="keep_latest")`. Idle deletion: `python -m agent_wf.state prune` finds threads whose newest checkpoint is older than `STATE_RETENTION_DAYS` (default 30) and deletes them with `adelete_thread`. It is a command rather than an in-app task so that it runs once, not once per instance. Age comes from the `ts` timestamp every checkpoint carries (`checkpoint->>'ts'`), so no schema of our own is added. The spike showed `aprune` frees rows but not disk until vacuum; autovacuum handles that and is left to the database.

**8. Migrations are a separate command.** `python -m agent_wf.state migrate` runs `setup()` with a retry on `UniqueViolation`, `DuplicateObject` and `DuplicateTable` (concurrent runs raised either; it is idempotent; spike: 8 of 8 succeed). Compose: a `db-migrate` one-shot service using the API image, `depends_on: app-db: service_healthy`; `api` depends on `db-migrate: service_completed_successfully`. At startup (`open_state`, before agents are built) the API only checks that the `checkpoint_migrations` table has the latest version known to the installed library and fails with "run the migration" otherwise. Alternative: `setup()` in lifespan, rejected by the spike (concurrent starts crash).

**9. Error mapping.** New `ApiError(409, "thread_busy", ...)` and a handler for `psycopg.OperationalError`, `psycopg_pool.PoolTimeout` and `psycopg.errors` raised in state operations to `ApiError(503, "state_unavailable", "The conversation store is unavailable")`; details are logged with the request ID. Only exceptions from state access are mapped (lock, repair, prune), not any exception from the agent run, so an LLM failure stays 502. Because the checkpointer is also called by the graph itself during the run, a saver failure inside `ainvoke` surfaces as the same psycopg exceptions and is mapped by the same handler.

**10. Settings** (only in `config.py`): `database_url: SecretStr | None`, `state_pool_size: int = 5`, `state_retention_days: int = 30`. The URL contains a password, so it is a `SecretStr` and never logged; startup errors name the setting only. `.env.example` and compose get the same names.

**11. Health.** `GET /` stays a pure liveness probe (state outages are 503 on the requests that need state; stateless requests keep working, and the container is not restarted for a database outage). A readiness endpoint is left out for now.

**12. Tests.** Unit tests use `InMemorySaver` as today. The lock, repair, prune and error mapping are written against small interfaces and unit tested with fakes. A `tests/db/` set (skipped unless `TEST_DATABASE_URL` is set; each test gets its own freshly created database) covers: restart continuity, parallel start (migrate by 8 at once), the 409, repair after cancel, `aprune` keeps messages, idle deletion. CI adds a `postgres:17` service to the `test` job and sets `TEST_DATABASE_URL`.

## Risks / Trade-offs

- Pool size caps concurrent conversation runs (each holds a connection for the lock for up to `AGENT_TIMEOUT_SECONDS`); instances x `STATE_POOL_SIZE` must stay under the database's `max_connections`. Documented, not enforced. A connection pooler (pgbouncer) in transaction mode would break session-level advisory locks.
- Repair adds an error `ToolMessage` the user never saw; the model may mention it. Accepted: it is truthful.
- Prune keeps only the latest checkpoint, so time-travel and per-step replay are not available. Accepted; nothing uses them.
- Conversations contain user text and tool output and sit in the database until retention; the 30-day default bounds it and is configurable. There is no per-conversation delete until a later change.
- The advisory-lock key is a 64-bit hash of the thread ID; two thread IDs colliding would only cause a spurious 409, with negligible probability.
- Age by the checkpoint's `ts` field relies on the library storing it in the checkpoint JSON; a database test pins it so a library upgrade that changes it fails loudly.
- Connecting from the API to `app-db` means `docker compose up` needs the new service healthy before the API starts, which lengthens startup slightly.

## Migration Plan

Deploy order: bring up `app-db`, run `migrate`, roll instances. Existing in-memory conversations are lost at the switch (as at any restart today). Rollback: unset `DATABASE_URL` to return to in-memory state; the database and its data are left untouched.

## Open Questions

- None blocking. A `DELETE /threads/{id}` endpoint and a readiness endpoint are deliberately deferred.
