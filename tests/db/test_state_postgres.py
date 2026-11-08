"""The state package against a real PostgreSQL (see conftest.py for how these are enabled)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from agent_wf.api.errors import ApiError
from agent_wf.state import (
    open_state,
    prune_idle,
    prune_thread,
    repair_thread,
    thread_lock,
)
from agent_wf.state.migrate import migrate
from agent_wf.state.store import check_schema, make_pool
from tests.fakes import FakeLLM


def run(coro):
    return asyncio.run(coro)


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def scripted(*answers):
    return FakeLLM(messages=iter(answers))


def human_texts(snapshot):
    return [m.content for m in snapshot.values["messages"] if m.type == "human"]


def test_open_state_refuses_an_unmigrated_database(db_settings):
    async def go():
        with pytest.raises(RuntimeError, match="run the migration"):
            async with open_state(db_settings):
                pass

    run(go())


def test_migrate_is_idempotent_and_survives_concurrent_runs(db_settings):
    async def go():
        await asyncio.gather(*(migrate(db_settings) for _ in range(8)))
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            await check_schema(state.pool)

    run(go())


def test_conversation_continues_after_a_restart(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            agent = create_agent(model=scripted(AIMessage("one")), tools=[], checkpointer=state.checkpointer)
            await agent.ainvoke({"messages": [("human", "first")]}, cfg("order-1"))
        async with open_state(db_settings) as state:  # a new process: new pool, new saver
            agent = create_agent(model=scripted(AIMessage("two")), tools=[], checkpointer=state.checkpointer)
            await agent.ainvoke({"messages": [("human", "second")]}, cfg("order-1"))
            other = await agent.aget_state(cfg("order-2"))
            return human_texts(await agent.aget_state(cfg("order-1"))), other.values

    texts, other = run(go())
    assert texts == ["first", "second"]
    assert not other


def test_lock_refuses_a_second_run_and_releases_afterwards(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            async with thread_lock(state, "t1"):
                with pytest.raises(ApiError) as busy:
                    async with thread_lock(state, "t1"):
                        pass
                async with thread_lock(state, "t2"):  # another thread is not affected
                    pass
            async with thread_lock(state, "t1"):  # free again once the first run ended
                pass
            return busy.value

    err = run(go())
    assert (err.status, err.code) == (409, "thread_busy")


def test_lock_is_released_when_the_run_is_cancelled(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:

            async def held():
                async with thread_lock(state, "t1"):
                    await asyncio.sleep(30)

            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.3):
                    await held()
            async with thread_lock(state, "t1"):
                pass

    run(go())


def test_lock_is_released_when_the_instance_dies(db_settings):
    """Session locks belong to the connection: when it is killed (a dead instance) the lock is freed."""

    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as dying, open_state(db_settings) as survivor:
            holding = asyncio.Event()

            async def held():
                async with thread_lock(dying, "t1"):
                    holding.set()
                    await asyncio.sleep(30)

            task = asyncio.create_task(held())
            await holding.wait()
            with pytest.raises(ApiError):
                async with thread_lock(survivor, "t1"):
                    pass
            async with survivor.pool.connection() as conn:  # the server drops the holder's connection
                await conn.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks "
                    "WHERE locktype = 'advisory' AND granted AND pid <> pg_backend_pid()"
                )
            async with thread_lock(survivor, "t1"):
                pass
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    run(go())


def test_cancelled_tool_call_is_repaired_and_the_thread_continues(db_settings):
    @tool
    async def slow_tool(x: int) -> str:
        """slow"""
        await asyncio.sleep(30)
        return "done"

    call = AIMessage(content="", tool_calls=[{"name": "slow_tool", "args": {"x": 1}, "id": "c1"}])

    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            agent = create_agent(model=scripted(call), tools=[slow_tool], checkpointer=state.checkpointer)
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.3):
                    await agent.ainvoke({"messages": [("human", "go")]}, cfg("t1"))
        async with open_state(db_settings) as state:  # after a restart the poisoned state is still there
            llm = scripted(AIMessage("recovered"))
            agent = create_agent(model=llm, tools=[slow_tool], checkpointer=state.checkpointer)
            assert await repair_thread(agent, cfg("t1")) == 1
            assert await repair_thread(agent, cfg("t1")) == 0  # a healthy history is left alone
            result = await agent.ainvoke({"messages": [("human", "again")]}, cfg("t1"))
            return result["messages"]

    messages = run(go())
    kinds = [(m.type, getattr(m, "status", None)) for m in messages]
    assert ("tool", "error") in kinds
    assert messages[-1].content == "recovered"


def test_prune_keeps_the_conversation_and_one_checkpoint(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            llm = scripted(*(AIMessage(f"r{i}") for i in range(10)))
            agent = create_agent(model=llm, tools=[], checkpointer=state.checkpointer)
            for i in range(5):
                await agent.ainvoke({"messages": [("human", f"q{i}")]}, cfg("long"))

            async def rows():
                async with state.pool.connection() as conn:
                    cur = await conn.execute("SELECT count(*) AS n FROM checkpoints WHERE thread_id = 'long'")
                    return (await cur.fetchone())["n"]

            before = await rows()
            await prune_thread(state.checkpointer, "long")
            after = await rows()
            await agent.ainvoke({"messages": [("human", "q5")]}, cfg("long"))
            return before, after, human_texts(await agent.aget_state(cfg("long")))

    before, after, texts = run(go())
    assert before > 1 and after == 1
    assert texts == ["q0", "q1", "q2", "q3", "q4", "q5"]


def test_idle_conversations_are_deleted_past_retention_only(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            llm = scripted(*(AIMessage("r") for _ in range(4)))
            agent = create_agent(model=llm, tools=[], checkpointer=state.checkpointer)
            for thread in ("old", "recent"):
                await agent.ainvoke({"messages": [("human", "hi")]}, cfg(thread))
            old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
            async with state.pool.connection() as conn:  # age the "old" thread: its checkpoints carry the time
                await conn.execute(
                    "UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{ts}', to_jsonb(%s::text)) "
                    "WHERE thread_id = 'old'",
                    (old,),
                )
            deleted = await prune_idle(state.checkpointer, state.pool, 30)
            kept = [t for t in ("old", "recent") if (await agent.aget_state(cfg(t))).values]
            return deleted, kept

    assert run(go()) == (1, ["recent"])


def test_checkpoint_rows_carry_a_timestamp_the_idle_query_relies_on(db_settings):
    async def go():
        await migrate(db_settings)
        async with open_state(db_settings) as state:
            agent = create_agent(model=scripted(AIMessage("r")), tools=[], checkpointer=state.checkpointer)
            await agent.ainvoke({"messages": [("human", "hi")]}, cfg(uuid.uuid4().hex))
            async with state.pool.connection() as conn:
                cur = await conn.execute("SELECT (checkpoint->>'ts')::timestamptz AS ts FROM checkpoints LIMIT 1")
                return (await cur.fetchone())["ts"]

    assert abs((datetime.now(UTC) - run(go())).total_seconds()) < 60


def test_state_failures_surface_as_database_errors(db_settings):
    """The API maps these exceptions to 503; here we only pin that a dead database raises them."""

    async def go():
        await migrate(db_settings)
        pool = make_pool(db_settings)
        await pool.open(wait=True)
        await pool.close()
        with pytest.raises(Exception) as err:
            async with pool.connection():
                pass
        return err.value

    assert run(go()) is not None and not (psycopg.Error is None)
