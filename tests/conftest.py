import pytest

from agent_wf.config import get_settings

TEST_API_KEY = "test-key"


def pytest_addoption(parser):
    # Registered here, not in tests/evals/: pytest only reads options from conftest files loaded
    # before it parses arguments, and this is the only one it loads for `testpaths = ["tests"]`.
    group = parser.getgroup("evals", "agent evals (run with: pytest -m eval)")
    group.addoption("--eval-repeats", type=int, default=3, help="runs per eval case (default 3)")
    group.addoption(
        "--eval-min-pass-rate",
        type=float,
        default=1.0,
        help="fraction of repeats that must pass for a case to pass (default 1.0)",
    )
    group.addoption("--eval-model", default=None, help="model to evaluate (default: LLM_MODEL setting)")
    group.addoption(
        "--eval-trace",
        action="store_true",
        default=False,
        help="send each eval repeat to Langfuse as a trace with an eval_pass score (needs Langfuse running)",
    )


@pytest.fixture
def app_env(monkeypatch):
    """Environment for tests that start the app: LLM key and API key present, tracing off."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-llm-key")
    monkeypatch.setenv("API_KEYS", TEST_API_KEY)
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_TRACING", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _started_client(monkeypatch, headers):
    from fastapi.testclient import TestClient

    import agent_wf.api.app as app_module
    from tests.fakes import fake_llm

    monkeypatch.setattr(app_module, "build_llm", lambda *a, **k: fake_llm())
    with TestClient(app_module.app, headers=headers, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def client(app_env, monkeypatch):
    """TestClient with a fake LLM, started through the real lifespan and sending the API key."""
    yield from _started_client(monkeypatch, {"X-API-Key": TEST_API_KEY})


@pytest.fixture
def anon_client(app_env, monkeypatch):
    """Same as `client` but sends no credentials."""
    yield from _started_client(monkeypatch, None)
