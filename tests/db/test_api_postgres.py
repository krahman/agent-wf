"""The HTTP API on a real PostgreSQL, started through the real lifespan."""

import asyncio
import threading
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

import agent_wf.api.app as app_module
from agent_wf.config import get_settings
from agent_wf.state import open_state
from agent_wf.state.migrate import migrate
from tests.conftest import TEST_API_KEY
from tests.fakes import FakeLLM, fake_llm

THREAD = {"configurable": {"thread_id": "t1"}}


@pytest.fixture
def pg_env(app_env, db_settings, db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("STATE_POOL_SIZE", "4")
    get_settings.cache_clear()
    asyncio.run(migrate(db_settings))
    monkeypatch.setattr(app_module, "build_llm", lambda *a, **k: fake_llm("hello"))
    return db_url


def started():
    return TestClient(app_module.app, headers={"X-API-Key": TEST_API_KEY}, raise_server_exceptions=False)


def saved_human_texts(db_settings, thread_id="t1"):
    async def go():
        async with open_state(db_settings) as state:
            saved = await state.checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
            if saved is None:
                return []
            return [m.content for m in saved.checkpoint["channel_values"]["messages"] if m.type == "human"]

    return asyncio.run(go())


def test_conversation_survives_a_restart_of_the_service(pg_env, db_settings):
    with started() as client:
        assert client.post("/agents/math", json={"prompt": "one", "thread_id": "t1"}).status_code == 200
    with started() as client:  # a new process
        assert client.post("/agents/math", json={"prompt": "two", "thread_id": "t1"}).status_code == 200
    assert saved_human_texts(db_settings) == ["one", "two"]


def test_requests_without_thread_id_leave_nothing_in_the_database(pg_env, db_settings):
    with started() as client:
        for _ in range(3):
            assert client.post("/agents/math", json={"prompt": "x"}).status_code == 200

    async def count():
        async with open_state(db_settings) as state, state.pool.connection() as conn:
            cur = await conn.execute("SELECT count(*) AS n FROM checkpoints")
            return (await cur.fetchone())["n"]

    assert asyncio.run(count()) == 0


def test_second_simultaneous_request_on_a_thread_is_refused_and_loses_nothing(pg_env, db_settings):
    @tool
    async def pause(x: int) -> str:
        """pause"""
        await asyncio.sleep(1.5)
        return "done"

    first = AIMessage(content="", tool_calls=[{"name": "pause", "args": {"x": 1}, "id": "c1"}])
    with started() as client:
        slow = create_agent(
            model=FakeLLM(messages=iter([first, AIMessage("finished"), AIMessage("again done")])),
            tools=[pause],
            checkpointer=client.app.state.state.checkpointer,
        )
        client.app.state.agents["math"] = slow
        results = {}

        def send(name, prompt):
            results[name] = client.post("/agents/math", json={"prompt": prompt, "thread_id": "t1"})

        a = threading.Thread(target=send, args=("a", "REQUEST A"))
        a.start()
        time.sleep(0.5)  # A is inside its tool call and holds the thread
        send("b", "REQUEST B")
        a.join()
        retry = client.post("/agents/math", json={"prompt": "REQUEST B again", "thread_id": "t1"})
    assert results["a"].status_code == 200
    assert results["b"].status_code == 409 and results["b"].json()["error"]["code"] == "thread_busy"
    assert retry.status_code == 200
    assert saved_human_texts(db_settings) == ["REQUEST A", "REQUEST B again"]


def test_run_cancelled_by_the_time_budget_does_not_break_the_thread(pg_env, db_settings, monkeypatch):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0.5")
    get_settings.cache_clear()

    @tool
    async def slow_tool(x: int) -> str:
        """slow"""
        await asyncio.sleep(30)
        return "done"

    start = AIMessage(content="", tool_calls=[{"name": "slow_tool", "args": {"x": 1}, "id": "c1"}])
    with started() as client:
        checkpointer = client.app.state.state.checkpointer
        client.app.state.agents["math"] = create_agent(
            model=FakeLLM(messages=iter([start])), tools=[slow_tool], checkpointer=checkpointer
        )
        assert client.post("/agents/math", json={"prompt": "go", "thread_id": "t1"}).status_code == 504
        client.app.state.agents["math"] = create_agent(
            model=FakeLLM(messages=iter([AIMessage("recovered")])), tools=[slow_tool], checkpointer=checkpointer
        )
        r = client.post("/agents/math", json={"prompt": "again", "thread_id": "t1"})
    assert r.status_code == 200 and r.json()["answer"] == "recovered"


def test_database_outage_is_503_for_conversations_only_and_clears_when_it_returns(pg_env, db_settings, db_url):
    with started() as client:
        assert client.post("/agents/math", json={"prompt": "one", "thread_id": "t1"}).status_code == 200
        with psycopg.connect(db_url, autocommit=True) as admin:  # drop every connection the service holds
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        codes = [
            client.post("/agents/math", json={"prompt": "x", "thread_id": "t1"}).status_code for _ in range(4)
        ]
        stateless = client.post("/agents/math", json={"prompt": "x"})
        body = client.post("/agents/math", json={"prompt": "x", "thread_id": "t1"})
    assert 503 in codes  # the dead connections are noticed ...
    assert codes[-1] == 200 and body.status_code == 200  # ... and replaced without a restart
    assert stateless.status_code == 200


def test_service_refuses_to_start_on_an_unmigrated_database(app_env, db_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    monkeypatch.setattr(app_module, "build_llm", lambda *a, **k: fake_llm())
    with pytest.raises(RuntimeError, match="run the migration"), started():
        pass
