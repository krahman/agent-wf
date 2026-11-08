import logging
from contextlib import AbstractContextManager, nullcontext

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

from agent_wf.config import Settings

logger = logging.getLogger("agent_wf.tracing")

_enabled = False


def configure_tracing(settings: Settings) -> None:
    """Initialise the Langfuse client when tracing is enabled and configured."""
    global _enabled
    _enabled = False
    if not settings.langfuse_tracing:
        logger.info("langfuse_tracing=False")
        return
    if not settings.langfuse_public_key or settings.langfuse_secret_key is None:
        logger.warning("LANGFUSE_TRACING is on but LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set; tracing disabled")
        return
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_host,
    )
    _enabled = True
    logger.info("langfuse_tracing=True host=%s", settings.langfuse_host)


def trace_callbacks() -> list[BaseCallbackHandler]:
    return [CallbackHandler()] if _enabled else []


def shutdown_tracing() -> None:
    """Flush buffered traces so none are lost on shutdown."""
    if _enabled:
        get_client().flush()


def trace_context(name: str, session_id: str) -> AbstractContextManager:
    """Name the trace and group it into a Langfuse session for everything run inside the block."""
    if not _enabled:
        return nullcontext()
    return propagate_attributes(trace_name=name, session_id=session_id)
