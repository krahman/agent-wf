"""Trace extraction and deterministic checks for agent evals. No model is involved here."""

import math
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field

_SHOW = 300


class ToolArgsCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    args: dict[str, Any]


class Checks(BaseModel):
    """Every field is optional; a case lists the checks it wants. Unknown names are rejected."""

    model_config = ConfigDict(extra="forbid")

    expect_tools: list[str] = Field(default_factory=list)
    forbid_tools: list[str] = Field(default_factory=list)
    tool_args: list[ToolArgsCheck] = Field(default_factory=list)
    answer_contains_any: list[str] = Field(default_factory=list)
    answer_contains_all: list[str] = Field(default_factory=list)
    answer_excludes: list[str] = Field(default_factory=list)
    max_tool_calls: int | None = None

    def is_empty(self) -> bool:
        return not self.model_dump(exclude_defaults=True)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class Trace:
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_outputs: list[tuple[str, str]] = field(default_factory=list)
    answer: str = ""

    def describe_calls(self) -> str:
        return "[" + ", ".join(f"{c.name}({c.args})" for c in self.tool_calls) + "]"


def extract_trace(messages: list[BaseMessage]) -> Trace:
    trace = Trace()
    for message in messages:
        if isinstance(message, AIMessage):
            trace.tool_calls.extend(ToolCall(tc["name"], dict(tc["args"])) for tc in message.tool_calls)
        elif isinstance(message, ToolMessage):
            trace.tool_outputs.append((message.name or "", str(message.content)))
    if messages and isinstance(messages[-1], AIMessage):
        trace.answer = messages[-1].text
    return trace


def _short(text: str) -> str:
    return text if len(text) <= _SHOW else text[:_SHOW] + "..."


def _values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_values_match(e, a) for e, a in zip(expected, actual))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(k in actual and _values_match(v, actual[k]) for k, v in expected.items())
    return expected == actual


def _args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return _values_match(expected, actual)


def run_checks(checks: Checks, trace: Trace) -> list[str]:
    """Return one human-readable failure per failed check; an empty list means the run passed."""
    failures: list[str] = []
    called = {c.name for c in trace.tool_calls}
    answer = trace.answer.casefold()

    for name in checks.expect_tools:
        if name not in called:
            failures.append(f"expect_tools: {name} was not called; calls were {trace.describe_calls()}")
    for name in checks.forbid_tools:
        if name in called:
            failures.append(f"forbid_tools: {name} was called; calls were {trace.describe_calls()}")
    for want in checks.tool_args:
        if not any(c.name == want.tool and _args_match(want.args, c.args) for c in trace.tool_calls):
            failures.append(
                f"tool_args: expected {want.tool} with {want.args}; actual calls were {trace.describe_calls()}"
            )
    if checks.answer_contains_any and not any(s.casefold() in answer for s in checks.answer_contains_any):
        failures.append(
            f"answer_contains_any: none of {checks.answer_contains_any} in answer: {_short(trace.answer)!r}"
        )
    for s in checks.answer_contains_all:
        if s.casefold() not in answer:
            failures.append(f"answer_contains_all: {s!r} missing from answer: {_short(trace.answer)!r}")
    for s in checks.answer_excludes:
        if s.casefold() in answer:
            failures.append(f"answer_excludes: {s!r} found in answer: {_short(trace.answer)!r}")
    if checks.max_tool_calls is not None and len(trace.tool_calls) > checks.max_tool_calls:
        failures.append(
            f"max_tool_calls: {len(trace.tool_calls)} calls exceeds {checks.max_tool_calls}; "
            f"calls were {trace.describe_calls()}"
        )
    return failures
