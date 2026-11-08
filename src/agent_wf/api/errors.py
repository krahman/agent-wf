import logging

import openai
import psycopg
import psycopg_pool
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.errors import GraphRecursionError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("agent_wf.api")

_HTTP_CODES = {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}
_MAX_MESSAGE = 300


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(
    request: Request, status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", "-"),
        }
    }
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return error_response(request, exc.status_code, code, str(exc.detail), exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    message = "Invalid request: " + "; ".join(parts)
    return error_response(request, 422, "invalid_request", message[:_MAX_MESSAGE])


async def _step_limit(request: Request, exc: GraphRecursionError) -> JSONResponse:
    logger.warning("agent reached its step limit: %s %s", request.method, request.url.path)
    return error_response(
        request, 422, "step_limit_exceeded", "The agent could not finish within its step limit"
    )


async def _upstream_error(request: Request, exc: openai.APIError) -> JSONResponse:
    # Provider details stay in the log; the caller only sees a generic message.
    logger.error("upstream LLM error: %s", type(exc).__name__, exc_info=exc)
    return error_response(
        request, 502, "upstream_error", "The language model provider failed to complete the request"
    )


async def _state_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # Driver messages carry the host and user name; they stay in the log.
    logger.error("conversation state store failed: %s", type(exc).__name__, exc_info=exc)
    return error_response(request, 503, "state_unavailable", "The conversation store is unavailable")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(GraphRecursionError, _step_limit)
    app.add_exception_handler(openai.APIError, _upstream_error)
    app.add_exception_handler(psycopg.Error, _state_unavailable)
    app.add_exception_handler(psycopg_pool.PoolTimeout, _state_unavailable)
