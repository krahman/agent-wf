import logging

from agent_wf.config import Settings
from agent_wf.observability import configure_tracing, trace_callbacks
from agent_wf.tools.math import add_numbers


def test_callback_logs_tool_call(caplog):
    from agent_wf.observability import LoggingCallbackHandler

    with caplog.at_level(logging.INFO, logger="agent_wf.agent"):
        add_numbers.invoke({"numbers": [1, 2]}, config={"callbacks": [LoggingCallbackHandler()]})
    text = caplog.text
    assert "tool_start name=add_numbers" in text and "tool_end name=add_numbers" in text


def test_request_id_header_roundtrip(client):
    r = client.get("/", headers={"x-request-id": "abc"})
    assert r.headers["x-request-id"] == "abc"
    assert client.get("/").headers["x-request-id"]


def test_tracing_disabled_by_default():
    configure_tracing(Settings(_env_file=None))
    assert trace_callbacks() == []


def test_tracing_requires_keys():
    configure_tracing(Settings(_env_file=None, langfuse_tracing=True))
    assert trace_callbacks() == []


def test_tracing_enabled_with_keys():
    configure_tracing(
        Settings(_env_file=None, langfuse_tracing=True, langfuse_public_key="pk", langfuse_secret_key="sk")
    )
    try:
        assert len(trace_callbacks()) == 1
    finally:
        configure_tracing(Settings(_env_file=None))


def test_empty_env_values_are_treated_as_unset(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    settings = Settings(_env_file=None)
    assert settings.langfuse_tracing is False and settings.langfuse_secret_key is None
