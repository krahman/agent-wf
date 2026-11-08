"""Opt-in Langfuse tracing for eval runs (`--eval-trace`). The application's own observability seam does
the sending; this module only decides whether a run may trace and fails fast when it cannot."""

import logging
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field

import httpx
import pytest
from langfuse import propagate_attributes

from agent_wf.config import Settings
from agent_wf.observability import configure_tracing, trace_callbacks

logger = logging.getLogger("agent_wf.evals")

HEALTH_TIMEOUT = 3  # seconds
SCORE_NAME = "eval_pass"
MAX_COMMENT = 500
SCORE_TIMEOUT = 3  # seconds


def require_langfuse(settings: Settings) -> None:
    """Stop the run before any model call when it cannot trace (names the problem, never a secret)."""
    missing = []
    if not settings.langfuse_public_key:
        missing.append("LANGFUSE_PUBLIC_KEY")
    if settings.langfuse_secret_key is None:
        missing.append("LANGFUSE_SECRET_KEY")
    if missing:
        pytest.exit(f"--eval-trace needs Langfuse, but {' and '.join(missing)} not set", returncode=2)
    url = settings.langfuse_host.rstrip("/") + "/api/public/health"
    try:
        httpx.get(url, timeout=HEALTH_TIMEOUT).raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        pytest.exit(f"--eval-trace needs Langfuse, but {settings.langfuse_host} is not reachable", returncode=2)


def start_tracing(trace_requested: bool, settings: Settings) -> bool:
    """Turn tracing on for this process if the run asked for it; returns whether it did.

    The flag is the opt-in, so it overrides LANGFUSE_TRACING=false in the configuration."""
    if not trace_requested:
        return False
    require_langfuse(settings)
    configure_tracing(settings.model_copy(update={"langfuse_tracing": True}))
    return True


@dataclass
class RepeatTrace:
    """What the runner needs from one traced repeat: the callbacks to pass to the agent, then the trace id."""

    callbacks: list
    trace_id: str | None = None


@dataclass
class Tracer:
    """Traces and scores the repeats of one eval run. Every Langfuse call is guarded: a failure here is
    logged and ignored, so tracing can never change whether a case passes.

    Traces go through the SDK. Scores go straight to Langfuse's REST API: the SDK's score batch is rejected
    by the self-hosted server this project runs (HTTP 400), while `POST /api/public/scores` is accepted."""

    run_id: str  # also the report's file stem: one report maps to one Langfuse session
    model: str
    host: str
    public_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    _scoring_failed: bool = field(default=False, init=False, repr=False)

    @contextmanager
    def repeat(self, case_id: str, repeat: int):
        try:
            handlers = trace_callbacks()
        except Exception:
            logger.warning("could not create the Langfuse handler; running this repeat untraced", exc_info=True)
            handlers = []
        trace = RepeatTrace(callbacks=handlers)
        try:
            attributes = propagate_attributes(
                trace_name=f"eval:{case_id}",
                session_id=self.run_id,
                tags=["eval", f"case:{case_id}", f"repeat:{repeat}", f"model:{self.model}"],
                metadata={"eval_case": case_id, "repeat": str(repeat), "model": self.model},
            )
        except Exception:
            logger.warning("could not set Langfuse trace attributes", exc_info=True)
            attributes = nullcontext()
        with attributes:
            yield trace
        trace.trace_id = _last_trace_id(handlers)

    def score(self, trace: RepeatTrace, failures: list[str]) -> None:
        """Record the repeat's result on its trace: boolean `eval_pass`, the failed checks as the comment.

        After the first failure no more scores are attempted, so one outage costs one timeout, not one per repeat."""
        if not trace.trace_id or self._scoring_failed:
            return
        body = {
            "name": SCORE_NAME,
            "value": 0 if failures else 1,
            "dataType": "BOOLEAN",
            "traceId": trace.trace_id,
        }
        if failures:
            body["comment"] = " | ".join(failures)[:MAX_COMMENT]
        try:
            response = httpx.post(
                f"{self.host.rstrip('/')}/api/public/scores",
                json=body,
                auth=(self.public_key, self.secret_key),
                timeout=SCORE_TIMEOUT,
            )
            response.raise_for_status()
        except Exception:
            self._scoring_failed = True
            logger.warning("could not record eval_pass scores in Langfuse; skipping the rest", exc_info=True)


def _last_trace_id(handlers: list) -> str | None:
    try:
        return handlers[0].last_trace_id if handlers else None
    except Exception:  # noqa: BLE001
        return None


def make_tracer(traced: bool, run_id: str, model: str, settings: Settings) -> Tracer | None:
    if not traced:
        return None
    secret = settings.langfuse_secret_key.get_secret_value() if settings.langfuse_secret_key else ""
    return Tracer(run_id, model, settings.langfuse_host, settings.langfuse_public_key or "", secret)
