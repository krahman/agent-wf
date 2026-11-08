from datetime import UTC, datetime

import pytest

from agent_wf.agents import AGENT_SPECS
from agent_wf.config import get_settings
from agent_wf.llm import build_llm
from agent_wf.observability import shutdown_tracing
from tests.evals import support, tracing
from tests.evals.report import run_id


@pytest.fixture(scope="session", autouse=True)
def _llm_key_present():
    support.require_llm_key(get_settings())


@pytest.fixture(scope="session", autouse=True)
def _run_clock():
    support.run_started = datetime.now(UTC)


@pytest.fixture(scope="session")
def eval_options(request):
    return support.eval_options_from(request.config)


@pytest.fixture(scope="session", autouse=True)
def tracer(_llm_key_present, _run_clock, eval_options):
    """The run's Langfuse tracer, or None unless `--eval-trace` was given."""
    settings = get_settings()
    traced = tracing.start_tracing(eval_options.trace, settings)
    model = eval_options.model or settings.llm_model
    yield tracing.make_tracer(traced, run_id(support.run_started, model), model, settings)
    if traced:
        shutdown_tracing()  # flush the buffered traces and scores


@pytest.fixture(scope="session", autouse=True)
def _wikipedia_stub():
    with support.wikipedia_stub():
        yield


@pytest.fixture(scope="session")
def agent_for(eval_options):
    built = {}

    def get(name: str):
        if name not in AGENT_SPECS:
            pytest.fail(f"unknown agent {name!r} in a case; known agents: {sorted(AGENT_SPECS)}", pytrace=False)
        if name not in built:
            built[name] = AGENT_SPECS[name].build(build_llm(eval_options.model, temperature=0))
        return built[name]

    return get


def pytest_sessionfinish(session, exitstatus):
    if not support.collected_results:
        return
    path = support.finish_session(
        support.collected_results,
        get_settings(),
        support.eval_options_from(session.config),
        started_at=support.run_started,
        traces=support.collected_traces,
    )
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter and path:
        reporter.write_line(f"eval report: {path}")
