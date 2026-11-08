"""`python -m agent_wf.state migrate|prune`: operator commands for the conversation state database."""

import argparse
import asyncio
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agent_wf.config import Settings
from agent_wf.state.migrate import migrate
from agent_wf.state.prune import prune_idle
from agent_wf.state.store import CONNECT_TIMEOUT, check_schema, make_pool


async def _prune(settings: Settings) -> int:
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    pool = make_pool(settings)
    await pool.open(wait=True, timeout=CONNECT_TIMEOUT)
    try:
        await check_schema(pool)
        return await prune_idle(AsyncPostgresSaver(pool), pool, settings.state_retention_days)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_wf.state", description=__doc__)
    parser.add_argument("command", choices=["migrate", "prune"])
    command = parser.parse_args(argv).command
    settings = Settings()
    try:
        if command == "migrate":
            asyncio.run(migrate(settings))
            print("state database is migrated")
        else:
            deleted = asyncio.run(_prune(settings))
            print(f"deleted {deleted} conversation(s) idle for more than {settings.state_retention_days} days")
    except Exception as exc:  # noqa: BLE001 - one line for the operator, never the connection string
        print(f"{command} failed: {type(exc).__name__}: {exc if isinstance(exc, RuntimeError) else 'see logs'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
