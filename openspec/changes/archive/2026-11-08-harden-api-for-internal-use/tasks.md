# Tasks

## 1. Configuration and startup validation

- [x] 1.1 Add `api_auth_enabled` (default true), `api_keys` (`SecretStr`, comma-separated, with a helper that returns the stripped non-empty keys), `max_prompt_chars` (4000) and `agent_timeout_seconds` (90) to `Settings` in `config.py`; verify a unit test covers parsing of `"a,b"`, `" a , b ,"`, empty and unset
- [x] 1.2 Add `check_startup(settings)` and call it first in `lifespan`: raise a clear error naming `OPENROUTER_API_KEY` when it is missing, and `API_KEYS` when auth is enabled with no key; log a warning when auth is disabled; verify tests assert each message names the setting and contains no secret value, and that a valid configuration starts
- [x] 1.3 Add the four new settings to `.env.example` (`API_KEYS` marked required) and add a `tests/conftest.py` fixture that sets a test key and clears the settings cache; verify `uv run pytest` still collects and runs

## 2. Error envelope

- [x] 2.1 Add `api/errors.py` with `ApiError(status, code, message)`, the `{"error": {code, message, request_id}}` builder and handlers for `ApiError`, Starlette `HTTPException` (fallback codes `not_found`, `method_not_allowed`, `http_error`) and `RequestValidationError` (`invalid_request`); store the request ID on `request.state` in `request_context`; raise `ApiError(404, "agent_not_found", ...)` for an unknown agent; verify tests for unknown agent, unknown route and a bad body check status, `error.code` and that `error.request_id` equals the `x-request-id` header
- [x] 2.2 Catch unexpected exceptions inside `request_context` (around `call_next`): return 500 `internal_error` in the envelope with the header set, and log the traceback with request and thread ID; verify a test that forces an exception in an endpoint sees status 500, a generic message, no exception text in the body, the `x-request-id` header, and the traceback in `caplog`
- [x] 2.3 Document the error shape and codes in `AGENTS.md`; verify the documented example matches an actual response from the test client

## 3. Access control

- [x] 3.1 Add `api/security.py` with an `APIKeyHeader("X-API-Key", auto_error=False)` dependency that compares with `hmac.compare_digest` against every configured key and raises `ApiError(401, "unauthorized", ...)`; attach it to a router holding `/chat` and `/agents/{name}`, leaving `/` outside; verify tests for missing key, wrong key, valid key, two configured keys (both work), a removed key (rejected), `/` open without a key, and 401 taking priority over a 422 body error
- [x] 3.2 Verify no key leaks: a test sends a wrong key and asserts neither `caplog` nor the response body contains it or any configured key; add a log line for rejected requests that records request ID and path only
- [x] 3.3 Honour `API_AUTH_ENABLED=false` (dependency becomes a no-op); update `tests/test_api.py` and `tests/test_observability.py` to send the key through the fixture; verify a disabled-auth test accepts keyless requests and the full existing suite passes
- [x] 3.4 Document the header, key rotation steps and the opt-out in `AGENTS.md`; verify by following the rotation steps against the test client

## 4. Limits and failure mapping

- [x] 4.1 Validate prompt length from `get_settings().max_prompt_chars` at validation time and constrain `thread_id` with `^[A-Za-z0-9_-]{1,64}$` in `api/schemas.py`; verify tests at 4000 and 4001 characters, valid and invalid thread IDs (space, newline, 65 characters), a generated ID when none is sent, and that a rejected request makes no LLM call (fake LLM call counter stays at zero)
- [x] 4.2 Wrap the agent call in `asyncio.timeout(agent_timeout_seconds)` and map the timeout to 504 `agent_timeout`; verify a test with a deliberately slow fake agent and a short budget gets 504 and the run is cancelled
- [x] 4.3 Map `GraphRecursionError` to 422 `step_limit_exceeded` and `openai.APIError` to 502 `upstream_error` with a generic message, logging the original exception; verify tests with a fake model that keeps requesting tools under a small recursion limit, and one that raises `openai.APIConnectionError` with a recognisable message that must not appear in the response
- [x] 4.4 Document the limits and the status table (401, 404, 422, 502, 504, 500) in `AGENTS.md`; verify each listed code appears in at least one test

## 5. Container

- [x] 5.1 Update the `Dockerfile`: create a system user (uid 10001), switch to it after the build steps, and add a `HEALTHCHECK` that requests `http://127.0.0.1:8000/` with Python's urllib; verify `docker build .` succeeds and `docker run --rm --entrypoint id <image> -u` prints `10001`
- [x] 5.2 Verify health reporting: start the `api` service with a test key and confirm `docker compose ps` reports it healthy; run the image with a command that never serves HTTP and short health-check overrides, and confirm it becomes unhealthy
- [x] 5.3 Note the non-root user and health check in `AGENTS.md`; verify the commands shown run as written

## 6. Integration

- [x] 6.1 Verify the CI parity commands pass: `uv sync --locked`, `uv run pytest`, `uv run ruff check`, `docker build .`, and `touch .env && docker compose config -q` from a clean copy with no `API_KEYS` set (the compose file must not require the key)
- [x] 6.2 Verify end to end through compose with a real key: no key gives 401 in the envelope; a valid key returns the correct answer for a math prompt; an oversize prompt gives 422; the container is healthy and runs as uid 10001; the call still appears as a trace in Langfuse

## Workflow follow-up

- Generate a key (`openssl rand -hex 32`) and add `API_KEYS=...` to your local `.env` and to the deployment's secret store. Without it the app refuses to start.
- Update internal callers to send `X-API-Key` and to read errors from `{"error": {...}}`.
- Archive this change after review. It is independent of `add-ci-pipeline`, which can be archived separately.
