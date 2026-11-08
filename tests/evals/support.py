"""Helpers for the eval runner. Kept importable (and unit tested) apart from the pytest wiring."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from agent_wf.config import Settings
from agent_wf.tools import wikipedia as wikipedia_tool
from tests.evals.cases import Case
from tests.evals.harness import extract_trace, run_checks
from tests.evals.report import (
    RESULTS_DIR,
    build_report,
    run_id,
    run_metadata,
    write_report,
)
from tests.evals.scoring import CaseResult
from tests.evals.tracing import Tracer

STUB_PASSAGE = (
    "The Eiffel Tower is a wrought-iron lattice tower in Paris, France. "
    "It is 330 metres (1,083 ft) tall."
)

# Results of every case run in this session, in order; read by the session-finish hook.
collected_results: list[CaseResult] = []


# Langfuse trace ids of each case's repeats, in order (only filled by a traced run).
collected_traces: dict[str, list[str | None]] = {}

# When this run started: set once per session and used for both the report name and the Langfuse session.
run_started: datetime | None = None


@dataclass(frozen=True)
class EvalOptions:
    repeats: int
    min_pass_rate: float
    model: str | None
    trace: bool = False


def eval_options_from(config) -> EvalOptions:
    repeats = config.getoption("--eval-repeats")
    rate = config.getoption("--eval-min-pass-rate")
    if repeats < 1:
        raise pytest.UsageError("--eval-repeats must be at least 1")
    if not 0 < rate <= 1:
        raise pytest.UsageError("--eval-min-pass-rate must be above 0 and at most 1")
    return EvalOptions(repeats, rate, config.getoption("--eval-model"), bool(config.getoption("--eval-trace")))


def require_llm_key(settings: Settings) -> None:
    """Abort the whole run before the first case when no key is set (names the setting, never a value)."""
    if settings.openrouter_api_key is None:
        pytest.exit("OPENROUTER_API_KEY is not set: the evals call a real model", returncode=2)


@contextmanager
def wikipedia_stub():
    """Replace only the network call inside the Wikipedia tool: the agent still sees the real tool."""
    stub_pages = [wikipedia_tool.Page("Eiffel Tower", STUB_PASSAGE)]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(wikipedia_tool, "fetch_pages", lambda query, client=None: stub_pages)
        yield


def run_case_once(case: Case, agent, recursion_limit: int, callbacks: list | None = None) -> list[str]:
    """Run the agent once; return failure reasons (empty when every check passed)."""
    config: dict = {"recursion_limit": recursion_limit}
    if callbacks:
        config["callbacks"] = callbacks
    try:
        result = agent.invoke({"messages": [("human", case.prompt)]}, config)
    except Exception as exc:  # noqa: BLE001 - any agent failure is a failed repeat, not a crashed run
        return [f"error: {type(exc).__name__}: {exc}"]
    return run_checks(case.checks, extract_trace(result["messages"]))


def run_repeat(
    case: Case, agent, recursion_limit: int, repeat: int, tracer: Tracer | None = None
) -> tuple[list[str], str | None]:
    """One repeat of a case, traced and scored in Langfuse when a tracer is given.

    Returns the failure reasons and the Langfuse trace id (None when untraced)."""
    if tracer is None:
        return run_case_once(case, agent, recursion_limit), None
    with tracer.repeat(case.id, repeat) as trace:
        failures = run_case_once(case, agent, recursion_limit, trace.callbacks)
    tracer.score(trace, failures)
    return failures, trace.trace_id


def finish_session(
    results: list[CaseResult],
    settings: Settings,
    options: EvalOptions,
    directory: Path = RESULTS_DIR,
    started_at: datetime | None = None,
    traces: dict[str, list[str | None]] | None = None,
) -> Path | None:
    """Write the report for this run; do nothing when no eval case ran."""
    if not results:
        return None
    metadata = run_metadata(settings, options.model, options.repeats, options.min_pass_rate, started_at)
    langfuse = None
    if options.trace:
        started = datetime.fromisoformat(metadata["started_at"])
        langfuse = {"host": settings.langfuse_host, "session_id": run_id(started, metadata["model"])}
    return write_report(build_report(metadata, results, langfuse, traces), directory)
