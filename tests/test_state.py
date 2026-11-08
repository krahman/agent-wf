"""Conversation state without a database: lock, repair, error mapping, and the in-memory fallback."""

import asyncio
import logging
from types import SimpleNamespace

import psycopg
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

import agent_wf.api.app as app_module
from agent_wf.api.errors import ApiError
from agent_wf.config import Settings
from agent_wf.state import open_state, repair_thread, thread_lock
from agent_wf.state.lock import lock_key
from agent_wf.state.repair import dangling_tool_calls
from agent_wf.state.store import State
from tests.fakes import FakeLLM, NoStateAgent, use_agent
from tests.test_limits import Recorder


def run(coro):
    return asyncio.run(coro)


def call(call_id):
    return AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": call_id}])


class UnreachableStore:
    """A pool whose database is gone."""

    def connection(self, *args, **kwargs):
        raise psycopg.OperationalError("connection to server at 10.1.2.3 failed: password for user app")


def test_dangling_tool_calls_finds_only_unanswered_calls():
    history = [HumanMessage("q"), call("a"), ToolMessage("r", tool_call_id="a"), call("b")]
    assert [c["id"] for c in dangling_tool_calls(history)] == ["b"]
    assert dangling_tool_calls(history[:3]) == []
    assert dangling_tool_calls([]) == []


def test_repair_closes_a_cancelled_tool_call_and_leaves_healthy_threads_alone():
    # Covered offline, not by `make eval`: a cancelled run needs a real timeout, which the eval harness
    # (sync, one run per case) cannot produce. Without the repair the real model answers this history with
    # HTTP 400 (confirmed once by hand against gpt-4o), so this guards the cause: a tool call with no result.
    @tool
    async def slow_tool(x: int) -> str:
        """slow"""
        await asyncio.sleep(30)
        return "done"

    start = AIMessage(content="", tool_calls=[{"name": "slow_tool", "args": {"x": 1}, "id": "c1"}])
    config = {"configurable": {"thread_id": "t1"}}

    async def go():
        saver = InMemorySaver()
        agent = create_agent(model=FakeLLM(messages=iter([start])), tools=[slow_tool], checkpointer=saver)
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.2):
                await agent.ainvoke({"messages": [("human", "go")]}, config)
        agent = create_agent(model=FakeLLM(messages=iter([AIMessage("ok")])), tools=[slow_tool], checkpointer=saver)
        closed = await repair_thread(agent, config)
        again = await repair_thread(agent, config)
        result = await agent.ainvoke({"messages": [("human", "again")]}, config)
        return closed, again, result["messages"]

    closed, again, messages = run(go())
    assert (closed, again) == (1, 0)
    assert any(m.type == "tool" and m.status == "error" for m in messages)
    assert messages[-1].content == "ok"


def test_memory_lock_refuses_a_second_run_and_releases():
    state = State(InMemorySaver())

    async def go():
        async with thread_lock(state, "t1"):
            with pytest.raises(ApiError) as busy:
                async with thread_lock(state, "t1"):
                    pass
            async with thread_lock(state, "t2"):
                pass
        async with thread_lock(state, "t1"):
            pass
        return busy.value

    err = run(go())
    assert (err.status, err.code) == (409, "thread_busy")


def test_lock_key_is_stable_and_distinct():
    assert lock_key("order-1") == lock_key("order-1")
    assert lock_key("order-1") != lock_key("order-2")
    assert -(2**63) <= lock_key("order-1") < 2**63


def test_busy_thread_is_409_with_the_error_envelope(client, monkeypatch):
    rec = Recorder()
    use_agent(client, rec)

    class Busy:
        async def __aenter__(self):
            raise ApiError(409, "thread_busy", "Another request on this thread is still running")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(app_module, "thread_lock", lambda state, thread_id: Busy())
    r = client.post("/agents/math", json={"prompt": "x", "thread_id": "t1"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "thread_busy"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    assert rec.calls == []


def test_unreachable_store_is_503_without_detail_and_makes_no_llm_call(client, caplog):
    rec = Recorder()
    use_agent(client, rec)
    client.app.state.state = SimpleNamespace(pool=UnreachableStore(), checkpointer=None)
    with caplog.at_level(logging.ERROR, logger="agent_wf.api"):
        r = client.post("/agents/math", json={"prompt": "x", "thread_id": "t1"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "state_unavailable"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    assert "10.1.2.3" not in r.text and "password" not in r.text
    assert rec.calls == []
    assert any("10.1.2.3" in str(rec_.exc_info[1]) for rec_ in caplog.records if rec_.exc_info)


def test_request_without_thread_id_does_not_need_the_database(client):
    rec = Recorder()
    use_agent(client, rec)
    client.app.state.state = SimpleNamespace(pool=UnreachableStore(), checkpointer=None)
    r = client.post("/agents/math", json={"prompt": "x"})
    assert r.status_code == 200
    assert len(rec.calls) == 1


def test_llm_failure_stays_502_not_503(client):
    import httpx
    import openai

    exc = openai.APIConnectionError(message="x", request=httpx.Request("POST", "https://p.example"))

    class Failing(NoStateAgent):
        async def ainvoke(self, *a, **k):
            raise exc

    use_agent(client, Failing())
    r = client.post("/agents/math", json={"prompt": "x", "thread_id": "t1"})
    assert r.status_code == 502


def test_conversation_continues_in_memory_without_a_database(client):
    r1 = client.post("/agents/math", json={"prompt": "one", "thread_id": "t1"})
    r2 = client.post("/agents/math", json={"prompt": "two", "thread_id": "t1"})
    assert r1.status_code == r2.status_code == 200
    saved = run(client.app.state.state.checkpointer.aget_tuple({"configurable": {"thread_id": "t1"}}))
    texts = [m.content for m in saved.checkpoint["channel_values"]["messages"] if m.type == "human"]
    assert texts == ["one", "two"]


def test_memory_mode_warns_that_conversations_are_not_durable(caplog):
    async def go():
        async with open_state(Settings(_env_file=None)) as state:
            return state.durable

    with caplog.at_level(logging.WARNING, logger="agent_wf.state"):
        assert run(go()) is False
    assert any("not durable" in r.getMessage() for r in caplog.records)


def test_unreachable_database_stops_startup_without_leaking_the_password(monkeypatch):
    monkeypatch.setattr("agent_wf.state.store.CONNECT_TIMEOUT", 0.5)
    settings = Settings(_env_file=None, database_url="postgresql://app:hunter2@127.0.0.1:1/none", state_pool_size=1)

    async def go():
        with pytest.raises(RuntimeError) as err:
            async with open_state(settings):
                pass
        return err.value

    err = run(go())
    assert "hunter2" not in str(err) and "hunter2" not in repr(err.__cause__)
    assert "DATABASE_URL" in str(err)
