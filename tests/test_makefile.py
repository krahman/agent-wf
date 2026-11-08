"""The Makefile, exercised with dry runs and copies in temporary folders. Offline; nothing real is touched."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = ROOT / "Makefile"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


# Variables the Makefile lets the environment override. `uv run pytest` itself exports UV (the path to
# uv), so without scrubbing them the recipes would show whatever the test run was launched with.
OVERRIDABLE = ("UV", "COMPOSE", "IMAGE", "API_URL", "ARGS", "CONFIRM", "GIT_SHA", "VERSION")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in OVERRIDABLE}
    return {**env, **extra}


def make(*args, cwd=ROOT, env=None):
    return subprocess.run(
        ["make", *args], check=False, cwd=cwd, capture_output=True, text=True,
        env=clean_env() if env is None else env, timeout=60,
    )


def dry(*args):
    result = make("-n", *args)
    assert result.returncode == 0, result.stderr
    return result.stdout


def targets():
    return re.findall(r"^([a-zA-Z_-]+):", MAKEFILE.read_text(), re.MULTILINE)


@pytest.fixture
def workdir(tmp_path):
    """A copy of the Makefile and the example env file, safe to run real targets in."""
    shutil.copy(MAKEFILE, tmp_path / "Makefile")
    shutil.copy(ROOT / ".env.example", tmp_path / ".env.example")
    return tmp_path


# --- discoverability


def test_no_target_prints_the_help_without_env_or_tools(workdir):
    # PATH without uv, git or docker: `make help` must not need them.
    result = make(cwd=workdir, env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr
    for name in targets():
        assert re.search(rf"^\s+{re.escape(name)}\s", result.stdout, re.MULTILINE), f"{name} missing from help"
    assert not (workdir / ".env").exists()


def test_every_target_is_documented_and_phony():
    text = MAKEFILE.read_text()
    phony = set(" ".join(re.findall(r"^\.PHONY:(.*)$", text, re.MULTILINE)).split())
    for line in re.findall(r"^[a-zA-Z_-]+:.*$", text, re.MULTILINE):
        name = line.split(":")[0]
        assert "## " in line, f"target {name} has no ## description"
        assert name in phony, f"target {name} is not .PHONY"
    assert set(targets()) == phony, "targets and .PHONY differ"


def test_default_goal_is_help():
    assert re.search(r"^\.DEFAULT_GOAL\s*:=\s*help\s*$", MAKEFILE.read_text(), re.MULTILINE)


# --- portability (GNU Make 3.81 is the macOS version)


@pytest.mark.parametrize("construct", [".ONESHELL", "$(file", "&:", "::=", "!=", ".SHELLFLAGS"])
def test_no_feature_newer_than_make_3_81(construct):
    code = "\n".join(line for line in MAKEFILE.read_text().splitlines() if not line.lstrip().startswith("#"))
    assert construct not in code


def test_phony_targets_run_even_when_a_directory_has_the_same_name(workdir):
    for name in ("test", "build", "check", "lint"):
        (workdir / name).mkdir()
    assert "pytest" in make("-n", "test", cwd=workdir).stdout


# --- arguments and overrides


def test_args_are_passed_to_test_fix_and_eval():
    assert "pytest -q -k limits" in dry("test", "ARGS=-k limits")
    assert "ruff check --fix --unsafe-fixes" in dry("fix", "ARGS=--unsafe-fixes")
    assert "pytest -m eval --eval-repeats 1" in dry("eval", "ARGS=--eval-repeats 1")
    assert 'pytest -m "eval and quick" --eval-repeats 1' in dry("eval-quick", "ARGS=--eval-repeats 1")


def test_tool_can_be_overridden():
    assert "uv --quiet run pytest" in dry("test", "UV=uv --quiet")
    assert "uv --quiet sync --locked" in dry("install", "UV=uv --quiet")


def test_core_targets_run_the_documented_commands():
    assert "uv sync --locked" in dry("install")
    assert "uv run pytest -q" in dry("test")
    assert "uv run ruff check" in dry("lint")
    assert "uv run pytest -m eval" in dry("eval")
    assert 'uv run pytest -m "eval and quick"' in dry("eval-quick")
    assert "pytest -m eval --collect-only -q" in dry("eval-list")
    assert "fastapi dev main.py" in dry("dev")
    assert "openspec validate --all --strict" in dry("spec-check")


# --- keygen and env


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed")
def test_keygen_prints_one_64_character_hex_key():
    first, second = make("keygen").stdout.strip(), make("keygen").stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", first) and first != second


def test_env_creates_the_file_from_the_example(workdir):
    result = make("env", cwd=workdir)
    assert result.returncode == 0 and "created .env" in result.stdout
    assert (workdir / ".env").read_text() == (workdir / ".env.example").read_text()


def test_env_never_overwrites_an_existing_file_and_prints_no_secret(workdir):
    (workdir / ".env").write_text("OPENROUTER_API_KEY=very-secret-value\n")
    result = make("env", cwd=workdir)
    assert "left unchanged" in result.stdout
    assert (workdir / ".env").read_text() == "OPENROUTER_API_KEY=very-secret-value\n"
    assert "very-secret-value" not in result.stdout + result.stderr


# --- clean


def test_clean_removes_only_caches_and_eval_reports(workdir):
    gone = [
        ".pytest_cache/v/cache",
        ".ruff_cache/0.1/x",
        "tests/evals/results/run.json",
        "src/pkg/__pycache__/mod.cpython-314.pyc",
        "tests/__pycache__/t.pyc",
    ]
    kept = [
        ".venv/lib/python3.14/__pycache__/keep.pyc",
        ".venv/bin/python",
        ".env",
        "src/pkg/mod.py",
        "tests/evals/cases.yaml",
        "tests/evals/test_agent_evals.py",
        "uv.lock",
        "pyproject.toml",
    ]
    for rel in gone + kept:
        path = workdir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    result = make("clean", cwd=workdir)
    assert result.returncode == 0, result.stderr
    assert not result.stderr.strip(), result.stderr
    for rel in gone:
        assert not (workdir / rel).exists(), f"{rel} should have been removed"
    for rel in kept:
        assert (workdir / rel).exists(), f"{rel} must be kept"


def test_clean_is_safe_to_run_twice_and_on_a_bare_checkout(workdir):
    assert make("clean", cwd=workdir).returncode == 0
    assert make("clean", cwd=workdir).returncode == 0


# --- docker targets


def fake_compose(directory):
    """A stand-in for `docker compose`: records whether .env existed, and what it was asked to do."""
    script = directory / "fake-compose"
    script.write_text(
        '#!/bin/sh\n[ -f .env ] && echo present >> env-seen.txt\necho "$@" >> compose-args.txt\nexit ${FAKE_RC:-0}\n'
    )
    script.chmod(0o755)
    return str(script)


def test_build_and_up_pass_the_commit_and_build_tags_the_version():
    build = dry("build", "GIT_SHA=abc1234", "IMAGE=myimage")
    assert "docker build --build-arg GIT_SHA=abc1234 -t myimage:" in build and build.strip().endswith(" .")
    assert "GIT_SHA=abc1234 docker compose up -d --build" in dry("up", "GIT_SHA=abc1234")


def test_migrate_and_prune_run_the_state_commands_in_the_compose_stack():
    assert dry("migrate").strip().endswith("docker compose run --rm db-migrate")
    assert dry("prune").strip().endswith("docker compose run --rm db-migrate python -m agent_wf.state prune")
    for name in ("migrate", "prune"):
        assert " -v" not in dry(name) and "down" not in dry(name)


def test_test_db_runs_the_db_tests_on_a_throwaway_container_and_always_removes_it():
    out = dry("test-db", "ARGS=-k lock")
    assert "docker run -d --rm --name agent-wf-test-db" in out
    assert "TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:54329/postgres" in out
    assert "pytest -q tests/db -k lock" in out
    assert out.rindex("docker stop agent-wf-test-db") > out.index("pytest"), "container is not stopped (and so removed) after the tests"
    assert "-p 127.0.0.1:" in out, "the test database must not listen on all interfaces"


def test_down_never_removes_volumes():
    out = dry("down")
    assert "docker compose down" in out and " -v" not in out


def test_only_reset_can_delete_volumes():
    text = MAKEFILE.read_text()
    assert text.count("down -v") == 1
    for dangerous in ("volume rm", "volume prune", "system prune", "docker rm", "docker volume"):
        assert dangerous not in text, dangerous
    reset_recipe = text[text.index("\nreset:") :].split("\n\n")[0]
    assert "down -v" in reset_recipe


def test_reset_without_confirm_refuses_and_runs_no_docker_command(workdir):
    compose = fake_compose(workdir)
    for args in ([], ["CONFIRM=no"], ["CONFIRM=YES"], ["CONFIRM=y"]):
        result = make("reset", f"COMPOSE={compose}", *args, cwd=workdir)
        assert result.returncode != 0, args
        assert "CONFIRM=yes" in result.stdout + result.stderr
    assert not (workdir / "compose-args.txt").exists(), "a docker command ran without confirmation"


def test_reset_with_confirm_removes_volumes(workdir):
    compose = fake_compose(workdir)
    assert make("reset", f"COMPOSE={compose}", "CONFIRM=yes", cwd=workdir).returncode == 0
    assert (workdir / "compose-args.txt").read_text().strip() == "down -v"


def test_compose_check_works_without_env_and_leaves_none_behind(workdir):
    compose = fake_compose(workdir)
    assert make("compose-check", f"COMPOSE={compose}", cwd=workdir).returncode == 0
    assert (workdir / "env-seen.txt").exists(), "compose ran without a .env to read"
    assert (workdir / "compose-args.txt").read_text().strip() == "config -q"
    assert not (workdir / ".env").exists()


def test_compose_check_keeps_an_existing_env_untouched(workdir):
    compose = fake_compose(workdir)
    (workdir / ".env").write_text("API_KEYS=secret-one\n")
    assert make("compose-check", f"COMPOSE={compose}", cwd=workdir).returncode == 0
    assert (workdir / ".env").read_text() == "API_KEYS=secret-one\n"


def test_compose_check_propagates_failure_and_still_cleans_up(workdir):
    compose = fake_compose(workdir)
    result = make("compose-check", f"COMPOSE={compose}", cwd=workdir, env=clean_env(FAKE_RC="3"))
    assert result.returncode != 0
    assert not (workdir / ".env").exists()


# --- check mirrors CI


def ci_commands():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    commands = []
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            for line in step.get("run", "").splitlines():
                if line.strip() and line.strip() != "touch .env":
                    commands.append(line.strip())
    return commands


def runs_exactly(output, command):
    """True if `command` appears as a whole command (not as the start of a longer one, e.g. with a path added)."""
    pattern = re.compile(rf"(^|[\s;{{]){re.escape(command)}\s*(;|\\|$)")
    return any(pattern.search(line) for line in output.splitlines())


def test_an_ambient_uv_variable_is_honoured_like_any_make_override():
    # uv exports UV=<path to uv> to the processes it runs; the Makefile's `UV ?= uv` respects it.
    result = subprocess.run(
        ["make", "-n", "install"], check=False, cwd=ROOT, capture_output=True, text=True,
        env=clean_env(UV="/custom/bin/uv"), timeout=60,
    )
    assert "/custom/bin/uv sync --locked" in result.stdout


def test_the_exact_match_helper_rejects_a_narrower_command():
    assert runs_exactly("uv run ruff check\n", "uv run ruff check")
    assert runs_exactly("uv run pytest -q \n", "uv run pytest -q")
    assert runs_exactly("\tdocker compose config -q; rc=$?; \\\n", "docker compose config -q")
    assert not runs_exactly("uv run ruff check src\n", "uv run ruff check")
    assert not runs_exactly("uv run pytest -q -x\n", "uv run pytest -q")


def test_check_runs_every_shell_command_ci_runs():
    commands = ci_commands()
    assert commands, "no run commands found in ci.yml: the parity test would be vacuous"
    out = dry("check")
    for command in commands:
        assert runs_exactly(out, command), f"CI runs `{command}` but `make check` does not run exactly that"
    assert "docker build" in out


def test_check_runs_the_checks_in_order():
    out = dry("check")
    markers = ["uv sync --locked", "uv run pytest -q", "uv run ruff check", "docker build", "config -q"]
    positions = [out.index(m) for m in markers]
    assert positions == sorted(positions), dict(zip(markers, positions))


def test_check_stops_at_the_first_failing_check_with_a_failure_status():
    result = make("check", "UV=false")
    assert result.returncode != 0
    assert "docker" not in result.stdout, "later checks ran after the first one failed"


def test_check_needs_no_env_file_and_no_key():
    # Everything check runs is either a tool call or the compose validation, which makes its own .env.
    assert "OPENROUTER_API_KEY" not in dry("check") and "API_KEYS" not in dry("check")
