"""The database tests are skipped offline, but must never be skipped silently where they are required (CI)."""

import os
import subprocess
import sys
from pathlib import Path


def run_db_tests(**env):
    base = {k: v for k, v in os.environ.items() if k not in ("TEST_DATABASE_URL", "REQUIRE_DB_TESTS")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/db", "-q", "-p", "no:cacheprovider"],
        check=False, env={**base, **env}, capture_output=True, text=True,
    )


def test_without_a_database_the_db_tests_are_skipped_and_the_run_passes():
    result = run_db_tests()
    assert result.returncode == 0, result.stdout
    assert "skipped" in result.stdout


def test_when_required_a_missing_database_fails_the_run():
    result = run_db_tests(REQUIRE_DB_TESTS="1")
    assert result.returncode != 0
    assert "REQUIRE_DB_TESTS is set but TEST_DATABASE_URL is not" in result.stdout + result.stderr


def test_ci_requires_the_database_tests():
    text = Path(".github/workflows/ci.yml").read_text()
    assert "REQUIRE_DB_TESTS" in text and "TEST_DATABASE_URL" in text
