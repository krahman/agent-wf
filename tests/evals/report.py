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


def run_metadata(settings: Settings, model: str | None, repeats: int, min_pass_rate: float) -> dict:
    """Chosen fields only: never the settings object, so no secret can reach the report."""
    return {
        "model": model or settings.llm_model,
        "version": __version__,
        "commit": settings.git_sha if settings.git_sha != "unknown" else _current_commit(),
        "repeats": repeats,
        "min_pass_rate": min_pass_rate,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def build_report(metadata: dict, results: list[CaseResult]) -> dict:
    return {
        **metadata,
        "passed": all(r.passed for r in results),
        "cases": [
            {
                "id": r.case_id,
                "passed": r.passed,
                "pass_rate": round(r.pass_rate, 4),
                "repeats": r.repeats,
                "passed_repeats": r.passed_repeats,
                "failures": [{"repeat": f.repeat, "reasons": f.reasons} for f in r.failures],
            }
            for r in results
        ],
    }


def write_report(report: dict, directory: Path = RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(report["started_at"]).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", report["model"]).strip("-")
    path = directory / f"{stamp}-{slug}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
