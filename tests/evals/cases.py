from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tests.evals.harness import Checks

CASES_FILE = Path(__file__).parent / "cases.yaml"


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    prompt: str = Field(min_length=1)
    agent: str = "math"
    tags: list[str] = Field(default_factory=list)
    checks: Checks

    @field_validator("checks")
    @classmethod
    def _at_least_one_check(cls, value: Checks) -> Checks:
        if value.is_empty():
            raise ValueError("a case needs at least one check")
        return value


def parse_cases(raw: object) -> list[Case]:
    if not isinstance(raw, list):
        raise TypeError("cases file must contain a list of cases")
    cases = [Case.model_validate(item) for item in raw]
    ids = [c.id for c in cases]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate case ids: {duplicates}")
    return cases


def load_cases(path: Path = CASES_FILE) -> list[Case]:
    return parse_cases(yaml.safe_load(path.read_text()))
