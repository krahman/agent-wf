import pytest
from langchain_core.messages import AIMessage


class Recorder:
    """Stands in for the LLM or an agent and records how it was called."""

    def __init__(self):
        self.calls = []

    async def ainvoke(self, payload, config=None):
        self.calls.append(config)
        return AIMessage("ok") if config is None else {"messages": [AIMessage("ok")]}


@pytest.fixture
def recorder(client):
    rec = Recorder()
    client.app.state.llm = rec
    client.app.state.agents["math"] = rec
    return rec


def test_prompt_at_limit_is_accepted(client, recorder):
    r = client.post("/agents/math", json={"prompt": "a" * 4000})
    assert r.status_code == 200 and len(recorder.calls) == 1


@pytest.mark.parametrize("path", ["/chat", "/agents/math"])
def test_prompt_over_limit_is_rejected_without_llm_call(client, recorder, path):
    r = client.post(path, json={"prompt": "a" * 4001})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert "4000" in r.json()["error"]["message"]
    assert recorder.calls == []


def test_prompt_limit_is_configurable(client, recorder, monkeypatch):
    from agent_wf.config import get_settings

    monkeypatch.setenv("MAX_PROMPT_CHARS", "10")
    get_settings.cache_clear()
    assert client.post("/chat", json={"prompt": "a" * 10}).status_code == 200
    assert client.post("/chat", json={"prompt": "a" * 11}).status_code == 422


def test_valid_thread_id_continues_the_conversation(client, recorder):
    for _ in range(2):
        r = client.post("/agents/math", json={"prompt": "x", "thread_id": "order-1234_a"})
        assert r.status_code == 200
    assert [c["configurable"]["thread_id"] for c in recorder.calls] == ["order-1234_a"] * 2


@pytest.mark.parametrize("bad", ["has space", "new\nline", "trailing-newline\n", "a" * 65, "semi;colon", ""])
def test_unsafe_thread_id_is_rejected_without_llm_call(client, recorder, bad):
    r = client.post("/agents/math", json={"prompt": "x", "thread_id": bad})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert recorder.calls == []


def test_thread_id_of_64_chars_is_accepted(client, recorder):
    assert client.post("/agents/math", json={"prompt": "x", "thread_id": "a" * 64}).status_code == 200


def test_missing_thread_id_gets_a_generated_one(client, recorder):
    client.post("/agents/math", json={"prompt": "x"})
    client.post("/agents/math", json={"prompt": "x"})
    ids = [c["configurable"]["thread_id"] for c in recorder.calls]
    assert all(ids) and ids[0] != ids[1]
