import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("agent_wf.agent")
_TOKEN_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens")


class LoggingCallbackHandler(BaseCallbackHandler):
    """Logs tool calls and LLM calls with their duration, errors and token usage."""

    def __init__(self) -> None:
        self._starts: dict[UUID, float] = {}
        self._tools: dict[UUID, str] = {}

    def _elapsed_ms(self, run_id: UUID) -> float:
        return (time.perf_counter() - self._starts.pop(run_id, time.perf_counter())) * 1000

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        self._starts[run_id] = time.perf_counter()
        self._tools[run_id] = name
        logger.info("tool_start name=%s input=%s", name, input_str)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        name = self._tools.pop(run_id, "unknown")
        logger.info("tool_end name=%s duration_ms=%.0f output=%s", name, self._elapsed_ms(run_id), output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        name = self._tools.pop(run_id, "unknown")
        logger.error("tool_error name=%s duration_ms=%.0f error=%r", name, self._elapsed_ms(run_id), error)

    def on_chat_model_start(self, serialized: dict[str, Any], messages: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_start(self, serialized: dict[str, Any], prompts: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage:
            for generations in response.generations:
                for gen in generations:
                    usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or usage
        tokens = {k: usage[k] for k in _TOKEN_KEYS if k in usage}
        logger.info("llm_end duration_ms=%.0f tokens=%s", self._elapsed_ms(run_id), tokens or "n/a")

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        logger.error("llm_error duration_ms=%.0f error=%r", self._elapsed_ms(run_id), error)
