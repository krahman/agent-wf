"""The shipped eval cases are well formed and cover what the spec requires. No model is involved."""

from agent_wf.agents import AGENT_SPECS
from agent_wf.tools import get_tools
from tests.evals.cases import load_cases

REQUIRED_TAGS = {
    "add", "subtract", "multiply", "divide", "power",
    "argument_order", "multi_step", "non_english", "separators", "negative",
    "divide_by_zero", "no_guess",
}


def test_cases_load_and_ids_are_unique():
    cases = load_cases()
    assert len(cases) >= 12
    assert len({c.id for c in cases}) == len(cases)


def test_every_required_category_is_covered():
    covered = {tag for c in load_cases() for tag in c.tags}
    assert REQUIRED_TAGS <= covered, f"missing: {sorted(REQUIRED_TAGS - covered)}"


def test_each_math_tool_is_expected_by_some_case():
    expected = {t for c in load_cases() for t in c.checks.expect_tools}
    assert {"add_numbers", "subtract_numbers", "multiply_numbers", "divide_numbers", "power_tool"} <= expected


def test_cases_only_name_agents_and_tools_that_exist():
    tools = {t.name for t in get_tools("math", "wikipedia")}
    for c in load_cases():
        assert c.agent in AGENT_SPECS, c.id
        named = {*c.checks.expect_tools, *c.checks.forbid_tools, *(t.tool for t in c.checks.tool_args)}
        assert named <= tools, f"{c.id}: unknown tools {sorted(named - tools)}"


def test_divide_by_zero_and_non_english_cases_match_the_spec():
    by_id = {c.id: c for c in load_cases()}
    nl = by_id["add-indonesian"]
    assert nl.prompt == "satu ditambah satu"
    assert nl.checks.tool_args[0].args == {"numbers": [1, 1]} and "2" in nl.checks.answer_contains_any
    tool_path = by_id["divide-by-zero-reports-the-error"].checks
    assert "divide_numbers" in tool_path.expect_tools and tool_path.tool_args[0].args == {"numbers": [100, 0]}
    direct = by_id["divide-by-zero-direct"].checks
    assert direct.expect_tools == [] and direct.answer_excludes
