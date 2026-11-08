"""Keep stored state bounded: latest checkpoint per thread, and no idle threads past retention."""

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger("agent_wf.state")

_IDLE_THREADS = """
SELECT thread_id FROM checkpoints
GROUP BY thread_id
HAVING max((checkpoint->>'ts')::timestamptz) < now() - make_interval(days => %s)
"""


async def prune_thread(checkpointer: BaseCheckpointSaver, thread_id: str) -> None:
    """Drop every checkpoint of the thread but the latest. Best effort: a failure is only logged."""
    try:
        await checkpointer.aprune([thread_id], strategy="keep_latest")
    except NotImplementedError:
        pass  # the in-memory saver has no pruning; it is for local development only
    except Exception:
        logger.exception("could not prune the thread's old checkpoints")


async def prune_idle(checkpointer: BaseCheckpointSaver, pool: AsyncConnectionPool, retention_days: int) -> int:
    """Delete threads idle longer than retention_days; return how many were deleted."""
    async with pool.connection() as conn:
        cur = await conn.execute(_IDLE_THREADS, (retention_days,))
        thread_ids = [row["thread_id"] for row in await cur.fetchall()]
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)
    return len(thread_ids)
