# Proposal

## Why

The API is open to anyone who can reach port 8000: `/chat` and `/agents/{name}` need no credentials and accept prompts of any length, so a single stray request can spend LLM credit or hold a worker for minutes. Failures are also opaque: hitting the agent step limit, an OpenRouter outage or a slow loop all surface as bare 500s with no stable error shape. The service is meant for internal callers (your own backend or a private network), so the goal is a modest, fail-closed baseline, not a public-internet defence. This is the next step on the production-readiness list after CI.

## What Changes

- Require a shared API key (`X-API-Key` header) on `/chat` and `/agents/{name}`. Several keys can be configured at once so a key can be rotated without downtime. The liveness endpoint `/` stays open.
- Fail closed: the app refuses to start when auth is enabled but no key is configured, or when the LLM key is missing. Running without auth needs an explicit opt-out.
- Cap input: prompts longer than a configured limit and `thread_id` values outside a safe format are rejected before any LLM call.
- Bound a run: an agent run that exceeds a configured time budget is cancelled and reported as a timeout.
- Return one JSON error shape for every failure, with a stable `code`, a safe message and the request ID. Map the step limit, run timeout, upstream LLM errors and unexpected errors to distinct statuses, and keep stack traces and provider messages out of responses (they are logged server-side). **BREAKING**: the 404 and 422 bodies change from FastAPI's `{"detail": ...}` to the new shape.
- Run the container as a non-root user and give the image a health check, which the compose `api` service inherits.
- Document the new settings in `.env.example` and `AGENTS.md`.

Out of scope, with the reason:
- Per-user identity, per-caller rate limits and thread ownership: callers are trusted internal services, and rate limiting belongs to the gateway in front of the API. Revisit if untrusted callers appear.
- A separate `/ready` endpoint: startup already fails fast on missing configuration, so a process that answers requests is ready.
- Request body size limits, TLS and securing `/docs`: handled by the gateway or reverse proxy for internal deployments.
- Durable conversation state and LLM-quality evals: separate planned changes.

## Capabilities

### New Capabilities
- `api-access-control`: which callers may use the agent endpoints, how they authenticate, and what happens with missing or wrong credentials.
- `request-limits`: bounds on prompt size, conversation ID format and run duration.
- `failure-handling`: the consistent error shape and the status each failure class maps to.
- `service-runtime`: how the service behaves at startup and in its container: fail-fast configuration, a non-root process and a health check.

### Modified Capabilities

None. There are no archived specs yet (`continuous-integration` from `add-ci-pipeline` is not archived).

## Impact

- Code: `api/app.py`, `api/schemas.py`, `config.py`, new `api/security.py` and `api/errors.py`; tests under `tests/` (existing API tests must send the key).
- Config: new settings `API_AUTH_ENABLED`, `API_KEYS`, `MAX_PROMPT_CHARS`, `AGENT_TIMEOUT_SECONDS`; `.env.example` and `AGENTS.md` updated.
- Container: `Dockerfile` (non-root user, `HEALTHCHECK`). `docker-compose.yml` needs no edit: it inherits the image health check and already passes `.env` through to the `api` service.
- Callers: must send `X-API-Key`, and must read errors from the new shape. You must add `API_KEYS` to your local `.env`; without it the app will not start (by design).
- CI is unaffected: the docker job only builds the image and validates the compose file, and neither needs the key.
- Observed while planning: `config.py` currently defaults `llm_model` from `os.getenv("OPENAPI_MODEL", ...)`, which reads an environment variable outside the settings mechanism. It is unrelated to this change and left alone.
