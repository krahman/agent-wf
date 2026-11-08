"""Create or upgrade the state schema. Run once, before the instances start (never from the API)."""

import asyncio

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent_wf.config import Settings
from agent_wf.state.store import CONNECT_TIMEOUT, make_pool

ATTEMPTS = 8
# What a concurrent run of the same migration raises: someone else is creating the object right now.
COLLISIONS = (
    psycopg.errors.UniqueViolation,
    psycopg.errors.DuplicateObject,
    psycopg.errors.DuplicateTable,
)


async def migrate(settings: Settings) -> None:
    """setup() is idempotent but two concurrent runs can collide on a catalog object; the loser retries."""
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    pool = make_pool(settings)
    await pool.open(wait=True, timeout=CONNECT_TIMEOUT)
    try:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                await AsyncPostgresSaver(pool).setup()
                return
            except COLLISIONS:
                if attempt == ATTEMPTS:
                    raise
                await asyncio.sleep(0.2 * attempt)
    finally:
        await pool.close()
