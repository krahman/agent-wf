# agent-wf

LangChain agents served by FastAPI, using OpenRouter as the LLM backend.

## Layout
- `main.py` — thin entrypoint (`uvicorn main:app`).
- `src/agent_wf/config.py` — typed `Settings` (env / `.env`); the only place env vars are read.
- `src/agent_wf/llm.py` — `build_llm()`, the only place a chat model is constructed.
- `src/agent_wf/tools/` — one module per domain, registered in `TOOLSETS` (`tools/__init__.py`).
- `src/agent_wf/agents/` — one `AgentSpec` per agent (prompt + toolset names), registered in `AGENT_SPECS`.
- `src/agent_wf/api/` — FastAPI app (agents are built in `lifespan`) and request/response schemas.
- `src/agent_wf/state/` — conversation state: `open_state` (Postgres pool + checkpointer, or in-memory), `thread_lock`, `repair_thread`, `prune_thread` / `prune_idle`, and the operator commands `python -m agent_wf.state migrate|prune`.
- `src/agent_wf/observability/` — `configure_logging` (request/thread IDs in every log line), `LoggingCallbackHandler` (tool and LLM calls: duration, errors, token usage), `configure_tracing` / `trace_callbacks` (Langfuse).
- `tests/` — pytest; no network or API key needed (`tests/db/` needs a Postgres and is skipped without `TEST_DATABASE_URL`). `examples/` — notebooks only.

## Conventions
- Tools take typed args via a pydantic `args_schema`, and return `{"result": ...}` or `{"error": "..."}`.
- No side effects at import time (no env reads, no client creation, no monkey-patching).
- Add an agent: create a spec in `agents/`, add it to `AGENT_SPECS`. Add tools: new module, add to `TOOLSETS`.

## Authentication
`/chat` and `/agents/{name}` require an `X-API-Key` header matching one of the keys in `API_KEYS` (comma-separated). `GET /` stays open for liveness probes. Missing or wrong key: 401 `unauthorized`, before any LLM call. Keys are never logged or returned.
- The app refuses to start when `API_KEYS` is empty. `API_AUTH_ENABLED=false` opts out (local dev only; logs a warning at startup).
- Rotate without downtime: add the new key (`API_KEYS=old,new`), restart, move callers to `new`, then remove `old` and restart. Generate keys with `openssl rand -hex 32`.

## Errors
Every error response is JSON: `{"error": {"code": "agent_not_found", "message": "Unknown agent 'nope'", "request_id": "..."}}`.
`request_id` equals the `x-request-id` response header. `code` is the stable identifier to branch on; `message` is safe to show. Stack traces and provider messages are never returned (they are logged server-side with the request ID).
| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | missing or invalid `X-API-Key` |
| 404 | `agent_not_found` / `not_found` | unknown agent / unknown route |
| 405 | `method_not_allowed` | wrong HTTP method |
| 409 | `thread_busy` | another run on the same `thread_id` is still in progress (retry later) |
| 422 | `invalid_request` | bad body: empty or over-long prompt, unsafe `thread_id` |
| 422 | `step_limit_exceeded` | agent hit `AGENT_RECURSION_LIMIT` |
| 503 | `state_unavailable` | the conversation database is unreachable (requests with a `thread_id` only; details are logged) |
| 502 | `upstream_error` | LLM provider failed (details are logged, never returned) |
| 504 | `agent_timeout` | run exceeded `AGENT_TIMEOUT_SECONDS` |
| 500 | `internal_error` | anything unexpected (traceback is logged with the request ID) |

Raise `ApiError(status, code, message)` from `api/errors.py` for new errors.

## Limits
- `prompt`: 1 to `MAX_PROMPT_CHARS` characters (default 4000).
- `thread_id`: optional, 1 to 64 characters of letters, digits, `-` and `_`. Without one the request keeps no conversation state (a stateless single run).
- One agent run is cancelled after `AGENT_TIMEOUT_SECONDS` (default 90), which bounds the whole loop; `LLM_TIMEOUT` bounds a single model call.
- Rate limiting and request body size are left to the gateway in front of the API.

## Conversation state
A request with a `thread_id` continues that conversation; one without it runs statelessly and stores nothing (no database needed either).
- **Store:** Postgres when `DATABASE_URL` is set (shared by all instances, survives restarts); otherwise process memory with a startup warning (local dev). The API refuses to start if a configured database is unreachable or not migrated. `STATE_POOL_SIZE` (default 5) connections per instance: instances x pool size must fit the database's `max_connections`, and each in-flight conversation run holds one connection (for its lock). Do not put a transaction-mode pooler in between (it breaks the locks).
- **Migrations are a separate step**, never run by the API: `make migrate` (compose runs the `db-migrate` one-shot service before `api` starts). Safe to repeat and to run concurrently.
- **One run per thread:** a Postgres advisory lock per `thread_id`; a second simultaneous request gets 409 `thread_busy` and loses nothing. The lock is freed when the run ends for any reason, or when the instance dies.
- **Repair:** before a run, tool calls left without a result (a run cancelled by the time budget or lost to a crash) get an error result. Without it the model rejects the thread's history (HTTP 400) forever.
- **Growth and retention:** after each run only the thread's latest checkpoint is kept. Threads idle longer than `STATE_RETENTION_DAYS` (default 30) are deleted by `make prune` / `python -m agent_wf.state prune`; run it on a schedule, once (not per instance). There is no per-conversation delete endpoint yet.
- **Outage:** requests with a `thread_id` get 503 `state_unavailable` and recover when the database returns; stateless requests and `GET /` are unaffected.
- Compose runs a separate `app-db` (own volume; password `APP_DB_PASSWORD`, local-dev default, use letters and digits only since it goes into a URL). `make reset` deletes it with the rest.
- Tests: unit tests use the in-memory store. `tests/db/` runs against a real Postgres, skipped (the `s` in pytest output) unless one is configured: `make test-db` starts a throwaway container, or set `TEST_DATABASE_URL=postgresql://user:pw@localhost:5432/postgres uv run pytest tests/db` (each test creates and drops its own database; CI provides a Postgres service).

## Wikipedia tool
`search_wikipedia` makes one request to Wikipedia's search API (`fetch_pages`, via `httpx`) and formats up to 3 intro summaries as `Page: <title>\nSummary: <text>`, capped at 4000 characters. Disambiguation pages are skipped; failures come back as `{"error": ...}`, never as exceptions. Requests time out after 10 s and are retried up to 3 times for network errors, 429 and 5xx.
- Wikipedia rate-limits or blocks (429/403) callers whose User-Agent has no contact info, so every request sends `agent_wf/<version> (+<WIKIPEDIA_CONTACT>)`. The default is this repository's URL; set `WIKIPEDIA_CONTACT` to your own URL or email for a deployment.
- The unit tests (`tests/test_wikipedia_tool.py`) use a mocked transport and prove nothing about the live API. After touching the tool, smoke test it: `uv run python -c "from agent_wf.tools.wikipedia import search_wikipedia as t; print(t.invoke({'query': 'Eiffel Tower'}))"` (expect `{'result': 'Page: Eiffel Tower...`, not an `error`).

## Observability
- Request middleware sets `x-request-id` (echoed in the response); `/agents/{name}` also sets the thread ID for logs.
- Langfuse (self-hosted, open source) is off by default. Enable with `LANGFUSE_TRACING=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (default `http://localhost:3000`). `thread_id` is sent as the Langfuse session ID. `LOG_LEVEL` sets the log level.
- `docker compose up --build` runs the API (:8000) and the full Langfuse stack (UI :3000, login `admin@example.com` / `admin12345`) with tracing preconfigured. Compose defaults are local-dev only; override secrets via `.env`.

## Container
The image runs as uid 10001 (not root) and has a `HEALTHCHECK` on `GET /`, which compose inherits: `docker compose ps` shows `healthy` once the API serves requests.
`docker compose up` needs `API_KEYS` (and `OPENROUTER_API_KEY`) in `.env`; without them the `api` container exits at startup with a message naming the missing setting. The `api` service waits for `app-db` to be healthy and for `db-migrate` to finish.
Check it: `docker compose ps api` and `docker exec agent-wf-api-1 id -u` (prints `10001`).

## Evals
Real-model checks of the agent's behaviour (which tools it calls, with what arguments, what it answers). They are opt-in: `uv run pytest` and CI never run them, call no LLM and need no key.
- Run all: `make eval` (`uv run pytest -m eval`; needs `OPENROUTER_API_KEY`; a run costs a few cents). **Quick check: `make eval-quick`** runs only the 3 cases tagged `quick` (about 20 s): `add-indonesian`, `subtract-argument-order`, `lookup-then-calculate`. Tag a case `quick` in `cases.yaml` to include it. One case: `make eval ARGS="-k divide-by-zero"`. List cases without running: `make eval-list`.
- Options: `--eval-repeats N` (default 3, run at temperature 0), `--eval-min-pass-rate R` (default 1.0; a case passes when this fraction of its repeats pass), `--eval-model NAME` (default `LLM_MODEL`; use it to compare models), `--eval-trace` (see below).
- Each run writes `tests/evals/results/<time>-<model>.json` (model, version, commit, per-case pass rate and failure reasons). It is gitignored; compare two reports after a prompt, tool or model change.
- The Wikipedia tool's network call (`fetch_pages` in `tools/wikipedia.py`) is stubbed with one fixed page (the Eiffel Tower); the real tool, its description and its formatting still run, so results do not depend on Wikipedia. The scoring logic has ordinary unit tests (`tests/test_eval_*.py`) that run in the default suite.

**Cases** live in `tests/evals/cases.yaml`. Add one whenever a change breaks something the suite did not catch.
```yaml
- id: subtract-argument-order
  prompt: What is 10 minus 3?
  tags: [subtract, argument_order]
  checks:
    expect_tools: [subtract_numbers]
    tool_args:
      - tool: subtract_numbers
        args: {numbers: [10, 3]}      # order matters here
    answer_number:
      - value: 7
- id: add-indonesian
  prompt: satu ditambah satu
  tags: [add, non_english]
  checks:
    expect_tools: [add_numbers]
    tool_args:
      - tool: add_numbers
        args: {numbers: [1, 1]}
        unordered: true               # addition is commutative: [1, 1] in any order
    answer_number:
      - value: 2
        words: [dua]                  # a spelled-out alternative (whole word)
    answer_excludes: [belas, puluh, ratus, ribu]   # rules out "dua belas" (12)
```
- Checks: `expect_tools`, `forbid_tools`, `tool_args`, `answer_number`, `answer_contains_any`, `answer_contains_all`, `answer_excludes`, `max_tool_calls`.
- **Numbers in answers use `answer_number`**, which compares values: `3500`, `3,500`, `3.500` and `3 500` are the same, and `6,25` is 6.25, but 2 never matches inside `12` or `20`. It proves the answer *states* the number somewhere, not that it is the final result, and an ambiguous token like `3.500` matches either reading (3500 or 3.5). Use `answer_contains_*` (case-insensitive substrings) only for phrases.
- `unordered: true` on a `tool_args` entry ignores the order of list arguments: use it for add and multiply, never for subtract or divide.

**Tracing evals in Langfuse** (opt-in): `make eval ARGS=--eval-trace`. Needs the Langfuse stack up (`make up`) and `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` in `.env`; it works even with `LANGFUSE_TRACING=false`, and a run that cannot trace stops before any model call. Every repeat becomes a trace named `eval:<case-id>`, all in one session named like the report file, tagged `eval`, `case:<id>`, `repeat:<n>` and `model:<name>`, with a boolean `eval_pass` score (false carries the failed checks as its comment). The report then also lists `langfuse.host`, `langfuse.session_id`, each case's `traces` and each failure's `trace_id`. A normal run sends nothing. Filter by the `eval` tag to find or delete eval traces.

## CI
`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. Three jobs, each reproducible locally:
- `test`: `uv sync --locked` then `uv run pytest` (needs no API key; fails if `uv.lock` is stale). A `postgres:17` service and `TEST_DATABASE_URL` let it run the `tests/db/` tests too, and `REQUIRE_DB_TESTS=1` makes a missing database fail the run instead of skipping those tests.
- `lint`: `uv run ruff check` (the `examples/` notebooks are excluded in `pyproject.toml`).
- `docker`: `docker build .` (nothing is pushed) and `touch .env && docker compose config -q`.

## Commands
The `Makefile` is the single list of project commands: `make help` shows every target. It works with GNU Make 3.81 (the version macOS ships).

| Target | What it does |
|---|---|
| `make install` | `uv sync --locked`, the same install CI does |
| `make lock` / `make version` | re-resolve dependencies and update `uv.lock` / print the project version |
| `make dev` | run the API locally with auto-reload (needs `.env`) |
| `make test` / `make test-db` / `make lint` / `make fix` | unit tests (offline) / the `tests/db/` tests on a throwaway Postgres container (needs Docker) / ruff check / ruff with `--fix` |
| `make check` | everything CI runs, in order: install, tests, lint, image build, compose validation. Needs Docker running, no key and no `.env`; for a quick loop without Docker use `make test lint` |
| `make eval` / `make eval-quick` / `make eval-list` | the real-model evals (a few cents per run) / only the 3 `quick` cases (about 20 s) / list the cases |
| `make smoke` | live check of the Wikipedia tool against the real API |
| `make build` | the image, tagged with the project version and git commit |
| `make up` / `down` / `logs` / `ps` / `health` | the compose stack (API, its conversation database and Langfuse): start, stop (data kept), follow logs, containers and health, probe `GET /` |
| `make migrate` / `make prune` | create or upgrade the conversation-state schema / delete conversations idle longer than `STATE_RETENTION_DAYS` |
| `make env` / `make keygen` | create `.env` from `.env.example` (never overwrites) / print a new `API_KEYS` value |
| `make spec-check` | validate all OpenSpec changes and specs |
| `make clean` / `make reset` | remove caches and eval reports / also delete the compose data volumes, including conversations and Langfuse traces and users (refuses without `CONFIRM=yes`) |

Conventions: `ARGS="..."` adds options to `test`, `test-db`, `fix`, `eval`, `eval-quick` and `logs` (`make test ARGS="-k limits"`, `make eval ARGS="--eval-repeats 1"`, `make logs ARGS=api`). `UV`, `COMPOSE` and `IMAGE` can be overridden. When CI gains a shell command, add it to `make check` (a test fails otherwise).
