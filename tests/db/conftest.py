"""Tests that need a real PostgreSQL: skipped unless TEST_DATABASE_URL points at one (CI provides it).
With REQUIRE_DB_TESTS=1 (set in CI) a missing database is an error instead, so a lost setting cannot turn
these tests into silent skips.

Each test gets its own freshly created database, so tests cannot see each other's conversations."""

import os
import uuid

import psycopg
import pytest
from psycopg import sql

from agent_wf.config import Settings

BASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    if BASE_URL:
        return
    if os.environ.get("REQUIRE_DB_TESTS"):
        raise pytest.UsageError("REQUIRE_DB_TESTS is set but TEST_DATABASE_URL is not: the database tests cannot run")
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL is not set")
    for item in items:
        if "tests/db/" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(skip)


def _with_database(url: str, name: str) -> str:
    return psycopg.conninfo.make_conninfo(url, dbname=name)


@pytest.fixture
def db_url():
    name = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(BASE_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    yield _with_database(BASE_URL, name)
    with psycopg.connect(BASE_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def db_settings(db_url):
    return Settings(_env_file=None, database_url=db_url, state_pool_size=4)
