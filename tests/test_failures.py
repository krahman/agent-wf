import itertools
import logging

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent_wf.agents import AGENT_SPECS
from agent_wf.config import get_settings
from tests.fakes import FakeLLM, NoStateAgent, use_agent


def looping_llm() -> FakeLLM:
    """A model that asks for the add_numbers tool forever."""
    calls = (
        AIMessage(content="", tool_calls=[{"name": "add_numbers", "args": {"numbers": [1, 1]}, "id": f"c{i}"}])
        for i in itertools.count()
    )
    return FakeLLM(messages=calls)


def test_step_limit_is_reported_as_422(client, monkeypatch):
    monkeypatch.setenv("AGENT_RECURSION_LIMIT", "3")
    get_settings.cache_clear()
    client.app.state.agents["math"] = AGENT_SPECS["math"].build(looping_llm(), InMemorySaver())
    r = client.post("/agents/math", json={"prompt": "x", "thread_id": "t-step"})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "step_limit_exceeded"
    assert error["request_id"] == r.headers["x-request-id"]
    assert "answer" not in r.json()


class FailingProvider(NoStateAgent):
    def __init__(self, exc):
        self.exc = exc

    async def ainvoke(self, *args, **kwargs):
        raise self.exc


REQUEST = httpx.Request("POST", "https://provider.example/v1/chat")
PROVIDER_ERRORS = [
    openai.APIConnectionError(message="provider-secret-detail: connection refused", request=REQUEST),
    openai.APITimeoutError(request=REQUEST),
]


@pytest.mark.parametrize("exc", PROVIDER_ERRORS, ids=lambda e: type(e).__name__)
@pytest.mark.parametrize("target", ["agent", "chat"])
def test_provider_failures_are_502_without_provider_detail(client, caplog, exc, target):
    if target == "agent":
        use_agent(client, FailingProvider(exc))
        path = "/agents/math"
    else:
        client.app.state.llm = FailingProvider(exc)
        path = "/chat"
    with caplog.at_level(logging.ERROR, logger="agent_wf.api"):
        r = client.post(path, json={"prompt": "x"})
    assert r.status_code == 502
    error = r.json()["error"]
    assert error["code"] == "upstream_error"
    assert "provider-secret-detail" not in r.text and "provider.example" not in r.text
    assert any(rec.exc_info for rec in caplog.records if "upstream LLM error" in rec.getMessage())
