import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from agent_wf import __version__
from agent_wf.config import Settings
from tests.evals.scoring import CaseResult

RESULTS_DIR = Path(__file__).parent / "results"


def _current_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_id(started_at: datetime, model: str) -> str:
    """Names the report file and the Langfuse session of one run, so each maps to exactly one of the other."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")
    return f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{slug}"


def run_metadata(
    settings: Settings,
    model: str | None,
    repeats: int,
    min_pass_rate: float,
    started_at: datetime | None = None,
) -> dict:
    """Chosen fields only: never the settings object, so no secret can reach the report."""
    return {
        "model": model or settings.llm_model,
        "version": __version__,
        "commit": settings.git_sha if settings.git_sha != "unknown" else _current_commit(),
        "repeats": repeats,
        "min_pass_rate": min_pass_rate,
        "started_at": (started_at or datetime.now(UTC)).isoformat(timespec="seconds"),
    }


def build_report(
    metadata: dict,
    results: list[CaseResult],
    langfuse: dict | None = None,
    traces: dict[str, list[str | None]] | None = None,
) -> dict:
    """`langfuse` (host and session id) and `traces` (each case's trace id per repeat) are given only for a
    traced run; an untraced report carries no trace fields at all."""
    report = {**metadata}
    report["passed"] = all(r.passed for r in results)
    if langfuse:
        report["langfuse"] = langfuse
    report["cases"] = [_case_entry(r, (traces or {}).get(r.case_id) if langfuse else None) for r in results]
    return report


def _case_entry(result: CaseResult, trace_ids: list[str | None] | None) -> dict:
    def failure(f) -> dict:
        entry = {"repeat": f.repeat, "reasons": f.reasons}
        if trace_ids and f.repeat <= len(trace_ids) and trace_ids[f.repeat - 1]:
            entry["trace_id"] = trace_ids[f.repeat - 1]
        return entry

    entry = {
        "id": result.case_id,
        "passed": result.passed,
        "pass_rate": round(result.pass_rate, 4),
        "repeats": result.repeats,
        "passed_repeats": result.passed_repeats,
    }
    if trace_ids is not None:
        entry["traces"] = trace_ids
    entry["failures"] = [failure(f) for f in result.failures]
    return entry


def write_report(report: dict, directory: Path = RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id(datetime.fromisoformat(report['started_at']), report['model'])}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
