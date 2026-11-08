"""One run per thread at a time, across instances (Postgres) or within the process (memory)."""

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agent_wf.api.errors import ApiError
from agent_wf.state.store import State

logger = logging.getLogger("agent_wf.state")

LOCK_WAIT = 5.0  # seconds to wait for a pooled connection before the store counts as unavailable
_memory_locks: dict[str, asyncio.Lock] = {}


def lock_key(thread_id: str) -> int:
    """Stable signed 64-bit advisory-lock key (Python's hash() differs per process)."""
    return int.from_bytes(hashlib.sha256(thread_id.encode()).digest()[:8], "big", signed=True)


def _busy() -> ApiError:
    return ApiError(409, "thread_busy", "Another request on this thread is still running")


@asynccontextmanager
async def thread_lock(state: State, thread_id: str) -> AsyncIterator[None]:
    if state.pool is None:
        lock = _memory_locks.setdefault(thread_id, asyncio.Lock())
        if lock.locked():
            raise _busy()
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            if not lock.locked():
                _memory_locks.pop(thread_id, None)
        return
    key = lock_key(thread_id)
    async with state.pool.connection(timeout=LOCK_WAIT) as conn:
        cur = await conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (key,))
        row = await cur.fetchone()
        if not row["got"]:
            raise _busy()
        try:
            yield
        finally:
            try:
                await conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
            except Exception:
                logger.exception("could not release the thread lock; closing its connection")
                await conn.close()
