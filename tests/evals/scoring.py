from dataclasses import dataclass, field


@dataclass(frozen=True)
class FailedRepeat:
    repeat: int  # 1-based
    reasons: list[str]


@dataclass
class CaseResult:
    case_id: str
    repeats: int
    passed_repeats: int
    pass_rate: float
    passed: bool
    failures: list[FailedRepeat] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.case_id}: {self.passed_repeats}/{self.repeats} passed ({self.pass_rate:.0%})"

    def failure_text(self) -> str:
        lines = [self.summary()]
        for failed in self.failures:
            lines.append(f"  repeat {failed.repeat}:")
            lines.extend(f"    - {reason}" for reason in failed.reasons)
        return "\n".join(lines)


def score_case(case_id: str, repeat_failures: list[list[str]], min_pass_rate: float) -> CaseResult:
    """`repeat_failures` has one entry per repeat: its failure reasons, empty when the repeat passed."""
    if not repeat_failures:
        raise ValueError("a case needs at least one repeat")
    total = len(repeat_failures)
    passed = sum(1 for reasons in repeat_failures if not reasons)
    rate = passed / total
    failures = [FailedRepeat(i, reasons) for i, reasons in enumerate(repeat_failures, 1) if reasons]
    return CaseResult(case_id, total, passed, rate, rate >= min_pass_rate - 1e-9, failures)
