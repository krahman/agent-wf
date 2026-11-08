"""Helpers for the eval runner. Kept importable (and unit tested) apart from the pytest wiring."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_community.utilities import WikipediaAPIWrapper

from agent_wf.config import Settings
from tests.evals.cases import Case
from tests.evals.harness import extract_trace, run_checks
from tests.evals.report import RESULTS_DIR, build_report, run_metadata, write_report
from tests.evals.scoring import CaseResult

STUB_PASSAGE = (
    "The Eiffel Tower is a wrought-iron lattice tower in Paris, France. "
    "It is 330 metres (1,083 ft) tall."
)

# Results of every case run in this session, in order; read by the session-finish hook.
collected_results: list[CaseResult] = []


@dataclass(frozen=True)
class EvalOptions:
    repeats: int
    min_pass_rate: float
    model: str | None


def eval_options_from(config) -> EvalOptions:
    repeats = config.getoption("--eval-repeats")
    rate = config.getoption("--eval-min-pass-rate")
    if repeats < 1:
        raise pytest.UsageError("--eval-repeats must be at least 1")
    if not 0 < rate <= 1:
        raise pytest.UsageError("--eval-min-pass-rate must be above 0 and at most 1")
    return EvalOptions(repeats, rate, config.getoption("--eval-model"))


def require_llm_key(settings: Settings) -> None:
    """Abort the whole run before the first case when no key is set (names the setting, never a value)."""
    if settings.openrouter_api_key is None:
        pytest.exit("OPENROUTER_API_KEY is not set: the evals call a real model", returncode=2)


@contextmanager
def wikipedia_stub():
    """Replace only the network call inside the Wikipedia tool: the agent still sees the real tool."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(WikipediaAPIWrapper, "run", lambda self, query: STUB_PASSAGE)
        yield


def run_case_once(case: Case, agent, recursion_limit: int) -> list[str]:
    """Run the agent once; return failure reasons (empty when every check passed)."""
    try:
        result = agent.invoke(
            {"messages": [("human", case.prompt)]}, {"recursion_limit": recursion_limit}
        )
    except Exception as exc:  # noqa: BLE001 - any agent failure is a failed repeat, not a crashed run
        return [f"error: {type(exc).__name__}: {exc}"]
    return run_checks(case.checks, extract_trace(result["messages"]))


def finish_session(
    results: list[CaseResult], settings: Settings, options: EvalOptions, directory: Path = RESULTS_DIR
) -> Path | None:
    """Write the report for this run; do nothing when no eval case ran."""
    if not results:
        return None
    metadata = run_metadata(settings, options.model, options.repeats, options.min_pass_rate)
    return write_report(build_report(metadata, results), directory)
