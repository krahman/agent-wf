import json

from agent_wf import __version__
from agent_wf.config import Settings
from tests.evals.report import build_report, run_metadata, write_report
from tests.evals.scoring import score_case

FAIL = ["tool_args: expected subtract_numbers with {'numbers': [10, 3]}; actual calls were []"]


def meta(**kw):
    settings = Settings(_env_file=None, git_sha="abc1234", **kw)
    return run_metadata(settings, "openai/gpt-4o", 3, 1.0)


def test_passing_run_report(tmp_path):
    report = build_report(meta(), [score_case("add", [[], [], []], 1.0)])
    path = write_report(report, tmp_path)
    data = json.loads(path.read_text())
    assert data["passed"] is True
    assert (data["model"], data["version"], data["commit"]) == ("openai/gpt-4o", __version__, "abc1234")
    assert (data["repeats"], data["min_pass_rate"]) == (3, 1.0) and data["started_at"]
    assert data["cases"][0] == {
        "id": "add", "passed": True, "pass_rate": 1.0, "repeats": 3, "passed_repeats": 3, "failures": [],
    }
    assert path.name.endswith("-openai-gpt-4o.json")


def test_failing_run_report_names_case_and_check(tmp_path):
    report = build_report(meta(), [score_case("add", [[], []], 1.0), score_case("sub", [FAIL, []], 1.0)])
    data = json.loads(write_report(report, tmp_path).read_text())
    assert data["passed"] is False
    failing = next(c for c in data["cases"] if c["id"] == "sub")
    assert failing["passed"] is False and failing["pass_rate"] == 0.5
    assert failing["failures"] == [{"repeat": 1, "reasons": FAIL}]


def test_model_override_is_recorded():
    settings = Settings(_env_file=None)
    assert run_metadata(settings, "other/model", 1, 0.5)["model"] == "other/model"
    assert run_metadata(settings, None, 1, 0.5)["model"] == settings.llm_model


def test_secrets_in_settings_never_reach_the_report(tmp_path):
    secrets = {
        "openrouter_api_key": "sk-or-secret-111",
        "api_keys": "api-secret-222",
        "langfuse_secret_key": "lf-secret-333",
        "langfuse_public_key": "pk-lf-444",
    }
    report = build_report(meta(**secrets), [score_case("add", [[]], 1.0)])
    text = write_report(report, tmp_path).read_text()
    for value in secrets.values():
        assert value not in text


def test_commit_falls_back_to_git_when_no_build_sha(monkeypatch):
    import subprocess

    from tests.evals import report

    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["git", "rev-parse", "--short"]
        return subprocess.CompletedProcess(cmd, 0, stdout="deadbee\n")

    monkeypatch.setattr(report.subprocess, "run", fake_run)
    assert run_metadata(Settings(_env_file=None), None, 1, 1.0)["commit"] == "deadbee"
    assert run_metadata(Settings(_env_file=None, git_sha="built1"), None, 1, 1.0)["commit"] == "built1"


def test_commit_is_unknown_when_git_is_unavailable(monkeypatch):
    from tests.evals import report

    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(report.subprocess, "run", boom)
    assert run_metadata(Settings(_env_file=None), None, 1, 1.0)["commit"] == "unknown"
