import pytest

from agent_wf.agents import AGENT_SPECS
from agent_wf.config import get_settings
from agent_wf.llm import build_llm
from tests.evals import support


@pytest.fixture(scope="session", autouse=True)
def _llm_key_present():
    support.require_llm_key(get_settings())


@pytest.fixture(scope="session", autouse=True)
def _wikipedia_stub():
    with support.wikipedia_stub():
        yield


@pytest.fixture(scope="session")
def eval_options(request):
    return support.eval_options_from(request.config)


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
        support.collected_results, get_settings(), support.eval_options_from(session.config)
    )
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter and path:
        reporter.write_line(f"eval report: {path}")
