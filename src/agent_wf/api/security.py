import hmac
import logging

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from agent_wf.api.errors import ApiError
from agent_wf.config import get_settings

logger = logging.getLogger("agent_wf.api")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(request: Request, key: str | None = Depends(_api_key_header)) -> None:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return
    submitted = (key or "").encode()
    # Compare against every configured key (no early exit) in constant time.
    matches = [hmac.compare_digest(submitted, k.encode()) for k in settings.api_key_list()]
    if key and any(matches):
        return
    logger.warning("auth rejected: %s %s", request.method, request.url.path)
    raise ApiError(401, "unauthorized", "Missing or invalid API key")
