# Design

## Context

See proposal.md for motivation and the four capability specs for required behaviour. Current state, verified in the code:

- `api/app.py` has two POST routes and `GET /`. There is no auth, `prompt` only has a minimum length, and `thread_id` is any string. The 404 is a plain `HTTPException`; nothing handles `GraphRecursionError` or provider errors, so both become 500s.
- `lifespan` builds the LLM and agents once. `build_llm()` already raises when the OpenRouter key is missing, so a missing key already stops startup (with a `RuntimeError`, not a clear config message).
- `Settings` (`config.py`) is the only place env vars are read; `env_ignore_empty=True` treats empty values as unset.
- `request_context` middleware sets the request ID and logs each request. Request ID and thread ID live in context variables used by the log formatter.
- Existing tests call the endpoints without credentials, so they must send a key after this change.
- The container runs as root and has no `HEALTHCHECK`; `docker-compose.yml` passes `.env` into the `api` service via `env_file`.
- Middleware order in Starlette: `ServerErrorMiddleware` (outermost, owns the catch-all `Exception` handler), then user middleware, then `ExceptionMiddleware` (owns handlers for specific exception classes), then the router.

## Goals / Non-Goals

**Goals:**
- A fail-closed baseline suitable for trusted internal callers, with one clear way to rotate keys.
- Every failure produces the same JSON shape, including 500s and including the request ID.
- No new infrastructure: no database, no external identity provider.

**Non-Goals:**
- Per-caller identity or per-caller limits; thread ownership; request body size limits; TLS; protecting `/docs` (see proposal).
- Changing how conversations are stored.

## Decisions

**1. Static shared API keys in `X-API-Key`, checked by a FastAPI dependency.**
`APIKeyHeader(auto_error=False)` gives the OpenAPI "Authorize" button, and a dependency attached to the router that holds `/chat` and `/agents/{name}` leaves `/` open without per-route code. Keys are compared with `hmac.compare_digest` against every configured key (no early exit on the first key). Alternatives: JWT or OAuth (needs an issuer and key distribution, overkill for internal callers); mTLS (belongs to the platform, not the app); `Authorization: Bearer` (equivalent, but loses the built-in OpenAPI scheme). Because auth is one dependency, swapping it for per-user identity later changes one function.

**2. Keys come from one setting, `API_KEYS`, comma-separated.**
Stored as `SecretStr` so it never prints in a repr or traceback; split, stripped and de-emptied on use. Several entries give zero-downtime rotation: add the new key, move callers over, remove the old key, restart. Alternatives: a file or secret-manager lookup (extra moving parts; platforms already inject secrets as env vars); a JSON list in the env var (awkward to type in `.env`).

**3. Fail closed, with an explicit opt-out.**
`API_AUTH_ENABLED` defaults to true. A `check_startup(settings)` function called first in `lifespan` raises a clear error when the LLM key is missing, or when auth is enabled and no key is set, naming the setting but never a value. `API_AUTH_ENABLED=false` runs without auth and logs a warning. Alternative: validate inside `Settings` as a model validator; rejected because every import of settings (tests, tooling) would then fail on a missing key.

**4. Input limits at the schema layer, driven by settings.**
The prompt length check is a validator that reads `get_settings().max_prompt_chars` when it runs (not at import), so the limit is configurable and failures come out as ordinary validation errors (422, code `invalid_request`). `thread_id` uses a fixed pattern `^[A-Za-z0-9_-]{1,64}$`: it ends up in logs and as a checkpointer key, so restricting it also prevents log injection and unbounded keys. Dependencies run before body validation, so an unauthenticated caller gets 401, not details about the schema.

**5. Run time budget with `asyncio.timeout`.**
The agent call is wrapped in `asyncio.timeout(agent_timeout_seconds)` (default 90 s), which cancels the run and maps to 504. It sits above the per-LLM-call `llm_timeout` (60 s): a loop of several model calls can exceed one call's timeout, and the budget bounds the total. Alternatives: rely only on the recursion limit (bounds steps, not time); rely only on `llm_timeout` (bounds one call, not the loop).

**6. One error envelope via an `ApiError` class and exception handlers.**
Own errors are raised as `ApiError(status, code, message)`. Handlers convert `ApiError`, Starlette `HTTPException` (fallback codes such as `not_found`), `RequestValidationError`, `GraphRecursionError` (422 `step_limit_exceeded`), `TimeoutError` from the budget (504 `agent_timeout`) and `openai.APIError` (502 `upstream_error`, generic message) into `{"error": {code, message, request_id}}`. The request ID is read from `request.state`, set by the middleware, because context variables set inside the app task do not propagate back. Alternatives: RFC 7807 `problem+json` (a standard, but heavier than needed for internal callers); keeping FastAPI's `{"detail": ...}` for built-in errors (two shapes to parse; rejected, accepting the breaking change).

**7. The catch-all 500 handler lives in the middleware.**
A handler registered for plain `Exception` runs in `ServerErrorMiddleware`, outside `request_context`, so the response would lack the `x-request-id` header and the request-log line. Wrapping `call_next` in `try/except Exception` inside `request_context` builds the envelope there, logs the full traceback with request ID and thread ID, and keeps the header. A test asserts the header is present on a 500.

**8. Non-root container and image-level health check.**
Dockerfile creates a system user (uid 10001) and sets `USER` after the build steps; the venv is read-only for it, and the app writes nothing. `HEALTHCHECK` runs a short `python -c` urllib request to `/` (the image has no curl or wget). Compose inherits the image check, so health state is defined once. Alternatives: a compose-only healthcheck (not covered when the image is run elsewhere); installing curl (extra package and attack surface).

## Risks / Trade-offs

- [Callers parse the old `{"detail": ...}` body] → Documented as **BREAKING** in the proposal; only internal callers exist. The `code` field is stable going forward.
- [A shared key cannot tell callers apart, and a leaked key works until rotated] → Rotation is supported by design; per-caller identity is a named follow-up if callers multiply.
- [Any key holder can still continue any thread by guessing its ID] → Accepted for trusted internal callers; random IDs are generated when none is supplied. Revisit with ownership if the caller set widens.
- [A cancelled or failed run may leave a partial conversation in the in-memory checkpointer] → The next call on that thread continues from that state. Documented; durable-state work can add cleanup.
- [`/docs` and `/openapi.json` stay open] → Reasonable on a private network; the gateway can restrict them.
- [Opting out of auth by mistake in production] → Off requires an explicit variable and logs a startup warning; the default is closed.

## Migration Plan

1. Generate a key (for example `openssl rand -hex 32`), add `API_KEYS` to the deployment's secrets and to local `.env`.
2. Update internal callers to send `X-API-Key` and to read errors from the new shape.
3. Deploy. Existing callers that were not updated will get 401, which is the intended signal.
4. Rollback: set `API_AUTH_ENABLED=false` temporarily (logs a warning) or redeploy the previous image; there is no data migration.

## Open Questions

- Are 4000 characters and 90 seconds the right defaults for the prompt cap and run budget? Both are settings, so adjusting them later does not change the specs or tasks.
