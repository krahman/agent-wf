import logging

from agent_wf.config import Settings

logger = logging.getLogger("agent_wf.api")


def check_startup(settings: Settings) -> None:
    """Refuse to start when required configuration is missing. Messages name settings, never values."""
    if settings.openrouter_api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    if not settings.api_auth_enabled:
        logger.warning("API_AUTH_ENABLED=false: agent endpoints accept requests without an API key")
    elif not settings.api_key_list():
        raise RuntimeError(
            "API_KEYS is not set: configure at least one key, "
            "or set API_AUTH_ENABLED=false to run without authentication"
        )
