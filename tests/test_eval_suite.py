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
    assert nl.checks.tool_args[0].args == {"numbers": [1, 1]}
    assert [(n.value, n.words) for n in nl.checks.answer_number] == [(2, ["dua"])]
    tool_path = by_id["divide-by-zero-reports-the-error"].checks
    assert "divide_numbers" in tool_path.expect_tools and tool_path.tool_args[0].args == {"numbers": [100, 0]}
    direct = by_id["divide-by-zero-direct"].checks
    assert direct.expect_tools == [] and direct.answer_excludes


# --- the shipped cases reject the wrong answers the old substring checks accepted


def replay(case_id, calls, answer):
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from tests.evals.harness import extract_trace, run_checks

    messages = [HumanMessage("prompt")]
    for i, (name, args) in enumerate(calls):
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}]))
        messages.append(ToolMessage(content='{"result": 0}', name=name, tool_call_id=f"c{i}"))
    messages.append(AIMessage(answer))
    case = {c.id: c for c in load_cases()}[case_id]
    return run_checks(case.checks, extract_trace(messages))


ADD_1_1 = [("add_numbers", {"numbers": [1, 1]})]


def test_add_indonesian_accepts_right_answers_in_digits_or_words():
    for right in ("Satu ditambah satu sama dengan dua.", "Hasilnya 2.", "1 + 1 = 2"):
        assert replay("add-indonesian", ADD_1_1, right) == [], right


def test_add_indonesian_rejects_the_answers_the_old_substring_check_accepted():
    for wrong in ("Satu ditambah satu sama dengan dua belas.", "The answer is 12.", "Hasilnya adalah 20."):
        assert replay("add-indonesian", ADD_1_1, wrong), f"{wrong!r} must fail"


def test_commutative_cases_accept_the_numbers_in_either_order():
    assert replay("multiply-basic", [("multiply_numbers", {"numbers": [7, 6]})], "6 times 7 is 42.") == []
    assert replay("multiply-basic", [("multiply_numbers", {"numbers": [6, 7]})], "42") == []


def test_order_sensitive_cases_still_reject_swapped_arguments():
    assert replay("subtract-argument-order", [("subtract_numbers", {"numbers": [3, 10]})], "7")
    assert replay("divide-argument-order", [("divide_numbers", {"numbers": [4, 25]})], "6.25")
    assert replay("subtract-argument-order", [("subtract_numbers", {"numbers": [10, 3]})], "The answer is 7.") == []


def test_number_formats_are_accepted_for_every_numeric_case():
    ok = replay("thousands-separators", [("add_numbers", {"numbers": [1000, 2500]})], "That makes 3,500.")
    assert ok == []
    for fmt in ("3.500", "3 500", "3500"):
        assert replay("thousands-separators", [("add_numbers", {"numbers": [2500, 1000]})], fmt) == [], fmt
    assert replay("thousands-separators", [("add_numbers", {"numbers": [1000, 2500]})], "That makes 35,000.")
    assert replay("divide-argument-order", [("divide_numbers", {"numbers": [25, 4]})], "It is 6,25.") == []
    assert replay("divide-argument-order", [("divide_numbers", {"numbers": [25, 4]})], "It is 625.")


def test_negative_number_case_accepts_symbols_and_words_but_not_the_positive():
    calls = [("add_numbers", {"numbers": [-5, 3]})]
    for right in ("The result is -2.", "The result is \u22122.", "That is minus 2.", "That is negative 2."):
        assert replay("negative-numbers", calls, right) == [], right
    assert replay("negative-numbers", calls, "The result is 2.")
