import pytest

from agent_wf.config import get_settings

TEST_API_KEY = "test-key"


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
