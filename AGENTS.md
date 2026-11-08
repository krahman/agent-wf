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

## Observability
- Request middleware sets `x-request-id` (echoed in the response); `/agents/{name}` also sets the thread ID for logs.
- Langfuse (self-hosted, open source) is off by default. Enable with `LANGFUSE_TRACING=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (default `http://localhost:3000`). `thread_id` is sent as the Langfuse session ID. `LOG_LEVEL` sets the log level.
- `docker compose up --build` runs the API (:8000) and the full Langfuse stack (UI :3000, login `admin@example.com` / `admin12345`) with tracing preconfigured. Compose defaults are local-dev only; override secrets via `.env`.

## Commands
- `uv sync` · `uv run pytest` · `uv run ruff check` · `uv run fastapi dev main.py`
