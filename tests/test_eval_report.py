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


# --- trace links (traced runs only)

TRACE_KEYS = {"langfuse", "traces", "trace_id"}


def all_keys(node):
    """Every dict key anywhere in a report."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from all_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from all_keys(item)


def traced_run(tmp_path, traces=None):
    from datetime import UTC, datetime

    from tests.evals import support

    started = datetime(2026, 11, 8, 9, 46, 12, tzinfo=UTC)
    results = [score_case("add", [[], [], []], 1.0), score_case("sub", [[], FAIL, []], 1.0)]
    traces = traces if traces is not None else {"add": ["t-a1", "t-a2", "t-a3"], "sub": ["t-s1", "t-s2", "t-s3"]}
    options = support.EvalOptions(repeats=3, min_pass_rate=1.0, model="openai/gpt-4o", trace=True)
    settings = Settings(_env_file=None, git_sha="abc", langfuse_host="http://lf.test:3000")
    path = support.finish_session(results, settings, options, tmp_path, started, traces)
    return path, json.loads(path.read_text())


def test_a_traced_report_names_the_session_the_host_and_every_repeats_trace(tmp_path):
    path, data = traced_run(tmp_path)
    assert data["langfuse"] == {"host": "http://lf.test:3000", "session_id": path.stem}
    assert path.stem == "20261108T094612Z-openai-gpt-4o"
    by_id = {c["id"]: c for c in data["cases"]}
    assert by_id["add"]["traces"] == ["t-a1", "t-a2", "t-a3"]
    assert by_id["sub"]["traces"] == ["t-s1", "t-s2", "t-s3"]


def test_a_failed_repeat_carries_its_own_trace_id(tmp_path):
    _, data = traced_run(tmp_path)
    failing = next(c for c in data["cases"] if c["id"] == "sub")
    assert failing["failures"] == [{"repeat": 2, "reasons": FAIL, "trace_id": "t-s2"}]


def test_a_repeat_without_a_trace_id_has_no_trace_id_field_but_keeps_its_slot(tmp_path):
    _, data = traced_run(tmp_path, traces={"add": ["t-a1", None, "t-a3"], "sub": ["t-s1", None, "t-s3"]})
    failing = next(c for c in data["cases"] if c["id"] == "sub")
    assert failing["traces"] == ["t-s1", None, "t-s3"]
    assert "trace_id" not in failing["failures"][0]


def test_an_untraced_report_has_no_trace_fields_at_all(tmp_path):
    from datetime import UTC, datetime

    from tests.evals import support

    results = [score_case("add", [[], []], 1.0), score_case("sub", [FAIL, []], 1.0)]
    options = support.EvalOptions(repeats=2, min_pass_rate=1.0, model="x/y")  # trace defaults to False
    settings = Settings(_env_file=None, git_sha="abc")
    stale_traces = {"add": ["should-not-appear"], "sub": ["nor-this"]}
    path = support.finish_session(results, settings, options, tmp_path, datetime(2026, 1, 1, tzinfo=UTC), stale_traces)
    data = json.loads(path.read_text())
    assert not TRACE_KEYS & set(all_keys(data)), set(all_keys(data))
    assert "should-not-appear" not in path.read_text()


def test_the_untraced_report_is_exactly_what_it_was_before_tracing_existed(tmp_path):
    report = build_report(meta(), [score_case("add", [[], FAIL], 1.0)])
    assert list(report) == ["model", "version", "commit", "repeats", "min_pass_rate", "started_at", "passed", "cases"]
    assert list(report["cases"][0]) == ["id", "passed", "pass_rate", "repeats", "passed_repeats", "failures"]
    assert list(report["cases"][0]["failures"][0]) == ["repeat", "reasons"]
