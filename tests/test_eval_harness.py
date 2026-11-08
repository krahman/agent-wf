from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tests.evals.harness import Checks, extract_trace, run_checks


def messages(*calls, answer="done"):
    """Build an agent message list: one AIMessage + ToolMessage per (tool, args), then the answer."""
    out = [HumanMessage("prompt")]
    for i, (name, args) in enumerate(calls):
        out.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}]))
        out.append(ToolMessage(content='{"result": 1}', name=name, tool_call_id=f"c{i}"))
    out.append(AIMessage(answer))
    return out


def failures(checks: dict, *calls, answer="done"):
    return run_checks(Checks(**checks), extract_trace(messages(*calls, answer=answer)))


# --- trace extraction


def test_trace_extraction():
    trace = extract_trace(messages(("add_numbers", {"numbers": [1, 1]}), answer="It is 2."))
    assert [(c.name, c.args) for c in trace.tool_calls] == [("add_numbers", {"numbers": [1, 1]})]
    assert trace.tool_outputs == [("add_numbers", '{"result": 1}')]
    assert trace.answer == "It is 2."


def test_trace_with_no_tools():
    trace = extract_trace([HumanMessage("hi"), AIMessage("hello")])
    assert trace.tool_calls == [] and trace.answer == "hello"


# --- expect_tools / forbid_tools


def test_expect_tools():
    assert failures({"expect_tools": ["add_numbers"]}, ("add_numbers", {"numbers": [1]})) == []
    out = failures({"expect_tools": ["add_numbers"]}, ("power_tool", {"base": 1, "exponent": 2}))
    assert len(out) == 1 and "add_numbers was not called" in out[0] and "power_tool" in out[0]


def test_forbid_tools():
    assert failures({"forbid_tools": ["search_wikipedia"]}) == []
    out = failures({"forbid_tools": ["add_numbers"]}, ("add_numbers", {"numbers": [1]}))
    assert len(out) == 1 and "forbid_tools" in out[0]


# --- tool_args


def tool_args(tool, args):
    return {"tool_args": [{"tool": tool, "args": args}]}


def test_tool_args_match_and_wrong_order_message():
    spec = tool_args("subtract_numbers", {"numbers": [10, 3]})
    assert failures(spec, ("subtract_numbers", {"numbers": [10, 3]})) == []
    out = failures(spec, ("subtract_numbers", {"numbers": [3, 10]}))
    assert len(out) == 1
    assert "[10, 3]" in out[0] and "[3, 10]" in out[0] and "subtract_numbers" in out[0]


def test_tool_args_numeric_tolerance_and_int_float():
    spec = tool_args("add_numbers", {"numbers": [1, 2.5]})
    assert failures(spec, ("add_numbers", {"numbers": [1.0, 2.5000000000001]})) == []
    assert failures(spec, ("add_numbers", {"numbers": [1, 2.6]})) != []


def test_tool_args_partial_match_ignores_extra_keys_and_matches_any_call():
    spec = tool_args("power_tool", {"base": 2})
    assert failures(spec, ("power_tool", {"base": 2, "exponent": 3})) == []
    two = (("power_tool", {"base": 5, "exponent": 1}), ("power_tool", {"base": 2, "exponent": 9}))
    assert failures(spec, *two) == []
    assert failures(tool_args("power_tool", {"base": 7}), *two) != []


def test_tool_args_list_length_matters_and_bool_is_not_a_number():
    assert failures(tool_args("add_numbers", {"numbers": [1, 2]}), ("add_numbers", {"numbers": [1, 2, 3]})) != []
    assert failures(tool_args("t", {"flag": True}), ("t", {"flag": 1})) != []


# --- answer checks


def test_answer_contains_any_is_case_insensitive():
    assert failures({"answer_contains_any": ["TWO", "2"]}, answer="The result is two.") == []
    out = failures({"answer_contains_any": ["6.25", "6,25"]}, answer="no idea")
    assert len(out) == 1 and "no idea" in out[0]


def test_answer_contains_all():
    assert failures({"answer_contains_all": ["zero", "cannot"]}, answer="You cannot divide by Zero") == []
    out = failures({"answer_contains_all": ["zero", "cannot"]}, answer="zero it is")
    assert len(out) == 1 and "'cannot' missing" in out[0]


def test_answer_excludes():
    assert failures({"answer_excludes": ["infinity"]}, answer="not possible") == []
    assert failures({"answer_excludes": ["infinity"]}, answer="It is Infinity") != []


def test_long_answers_are_truncated_in_messages():
    out = failures({"answer_contains_all": ["needle"]}, answer="x" * 1000)
    assert len(out[0]) < 500


# --- max_tool_calls


def test_max_tool_calls():
    calls = (("add_numbers", {"numbers": [1]}), ("add_numbers", {"numbers": [2]}))
    assert failures({"max_tool_calls": 2}, *calls) == []
    out = failures({"max_tool_calls": 1}, *calls)
    assert len(out) == 1 and "2 calls exceeds 1" in out[0]


def test_multiple_failures_are_all_reported():
    out = failures({"expect_tools": ["add_numbers"], "answer_contains_any": ["2"]}, answer="nope")
    assert len(out) == 2


def test_empty_checks_detected():
    assert Checks().is_empty() and not Checks(max_tool_calls=1).is_empty()
