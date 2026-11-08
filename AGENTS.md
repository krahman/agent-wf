# agent-wf

LangChain agents served by FastAPI, using OpenRouter as the LLM backend.

## Layout
- `main.py` — thin entrypoint (`uvicorn main:app`).
- `src/agent_wf/config.py` — typed `Settings` (env / `.env`); the only place env vars are read.
- `src/agent_wf/llm.py` — `build_llm()`, the only place a chat model is constructed.
- `src/agent_wf/tools/` — one module per domain, registered in `TOOLSETS` (`tools/__init__.py`).
- `src/agent_wf/agents/` — one `AgentSpec` per agent (prompt + toolset names), registered in `AGENT_SPECS`.
- `src/agent_wf/api/` — FastAPI app (agents are built in `lifespan`) and request/response schemas.
- `src/agent_wf/observability/` — `configure_logging` (request/thread IDs in every log line), `LoggingCallbackHandler` (tool and LLM calls: duration, errors, token usage), `configure_tracing` / `trace_callbacks` (Langfuse).
- `tests/` — pytest; no network or API key needed. `examples/` — notebooks only.

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
| 422 | `invalid_request` | bad body: empty or over-long prompt, unsafe `thread_id` |
| 422 | `step_limit_exceeded` | agent hit `AGENT_RECURSION_LIMIT` |
| 502 | `upstream_error` | LLM provider failed (details are logged, never returned) |
| 504 | `agent_timeout` | run exceeded `AGENT_TIMEOUT_SECONDS` |
| 500 | `internal_error` | anything unexpected (traceback is logged with the request ID) |

Raise `ApiError(status, code, message)` from `api/errors.py` for new errors.

## Limits
- `prompt`: 1 to `MAX_PROMPT_CHARS` characters (default 4000).
- `thread_id`: optional, 1 to 64 characters of letters, digits, `-` and `_`; generated when omitted.
- One agent run is cancelled after `AGENT_TIMEOUT_SECONDS` (default 90), which bounds the whole loop; `LLM_TIMEOUT` bounds a single model call.
- Rate limiting and request body size are left to the gateway in front of the API.

## Observability
- Request middleware sets `x-request-id` (echoed in the response); `/agents/{name}` also sets the thread ID for logs.
- Langfuse (self-hosted, open source) is off by default. Enable with `LANGFUSE_TRACING=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (default `http://localhost:3000`). `thread_id` is sent as the Langfuse session ID. `LOG_LEVEL` sets the log level.
- `docker compose up --build` runs the API (:8000) and the full Langfuse stack (UI :3000, login `admin@example.com` / `admin12345`) with tracing preconfigured. Compose defaults are local-dev only; override secrets via `.env`.

## Container
The image runs as uid 10001 (not root) and has a `HEALTHCHECK` on `GET /`, which compose inherits: `docker compose ps` shows `healthy` once the API serves requests.
`docker compose up` needs `API_KEYS` (and `OPENROUTER_API_KEY`) in `.env`; without them the `api` container exits at startup with a message naming the missing setting.
Check it: `docker compose ps api` and `docker exec agent-wf-api-1 id -u` (prints `10001`).

## CI
`.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. Three jobs, each reproducible locally:
- `test`: `uv sync --locked` then `uv run pytest` (needs no API key; fails if `uv.lock` is stale).
- `lint`: `uv run ruff check` (the `examples/` notebooks are excluded in `pyproject.toml`).
- `docker`: `docker build .` (nothing is pushed) and `touch .env && docker compose config -q`.

## Commands
- `uv sync` · `uv run pytest` · `uv run ruff check` · `uv run fastapi dev main.py`
