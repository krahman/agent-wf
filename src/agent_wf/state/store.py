"""Where conversation state lives: Postgres when DATABASE_URL is set, process memory otherwise."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from agent_wf.config import Settings

logger = logging.getLogger("agent_wf.state")

CONNECT_TIMEOUT = 10.0
_POOL_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


@dataclass
class State:
    """The checkpointer agents use, plus the pool behind it (None when state is in memory)."""

    checkpointer: BaseCheckpointSaver
    pool: AsyncConnectionPool | None = None

    @property
    def durable(self) -> bool:
        return self.pool is not None


def make_pool(settings: Settings) -> AsyncConnectionPool:
    assert settings.database_url is not None
    return AsyncConnectionPool(
        settings.database_url.get_secret_value(),
        min_size=1,
        max_size=settings.state_pool_size,
        open=False,
        kwargs=_POOL_KWARGS,
    )


async def check_schema(pool: AsyncConnectionPool) -> None:
    """Fail unless the schema was migrated to the version the installed library expects."""
    expected = len(AsyncPostgresSaver.MIGRATIONS) - 1
    try:
        async with pool.connection() as conn:
            cur = await conn.execute("SELECT max(v) AS v FROM checkpoint_migrations")
            row = await cur.fetchone()
    except Exception as exc:
        raise RuntimeError(
            "the conversation state database has no migrated schema: run the migration (make migrate)"
        ) from exc
    current = row["v"] if row and row["v"] is not None else -1
    if current < expected:
        raise RuntimeError(
            f"the conversation state schema is at version {current}, expected {expected}: "
            "run the migration (make migrate)"
        )


@asynccontextmanager
async def open_state(settings: Settings) -> AsyncIterator[State]:
    """Open conversation state for the app's lifetime; errors never contain the database URL."""
    if settings.database_url is None:
        logger.warning("DATABASE_URL is not set: conversations are kept in memory and are not durable")
        yield State(InMemorySaver())
        return
    pool = make_pool(settings)
    try:
        await pool.open(wait=True, timeout=CONNECT_TIMEOUT)
    except Exception:  # noqa: BLE001 - the driver message can carry the host and user
        await pool.close()
        raise RuntimeError("DATABASE_URL is set but the conversation state database cannot be reached") from None
    try:
        await check_schema(pool)
        yield State(AsyncPostgresSaver(pool), pool)
    finally:
        await pool.close()
