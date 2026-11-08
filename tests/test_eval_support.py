import socket

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_wf.config import Settings
from agent_wf.tools.wikipedia import search_wikipedia
from tests.evals import support
from tests.evals.cases import Case
from tests.evals.harness import Checks

# --- missing key aborts the run, naming the setting and no value


def test_missing_llm_key_exits_naming_the_setting():
    settings = Settings(_env_file=None, api_keys="secret-api-key")
    with pytest.raises(pytest.exit.Exception) as exc:
        support.require_llm_key(settings)
    assert "OPENROUTER_API_KEY" in str(exc.value)
    assert "secret-api-key" not in str(exc.value)
    assert exc.value.returncode == 2


def test_present_llm_key_passes():
    support.require_llm_key(Settings(_env_file=None, openrouter_api_key="k"))


# --- the Wikipedia stub replaces only the network call


def test_wikipedia_tool_returns_the_fixed_passage_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    with support.wikipedia_stub():
        assert search_wikipedia.invoke({"query": "anything"}) == {"result": support.STUB_PASSAGE}
        assert search_wikipedia.name == "search_wikipedia"  # the real tool, not a fake


def test_stub_is_removed_afterwards():
    from langchain_community.utilities import WikipediaAPIWrapper

    original = WikipediaAPIWrapper.run
    with support.wikipedia_stub():
        assert WikipediaAPIWrapper.run is not original
    assert WikipediaAPIWrapper.run is original


# --- one run of one case


def case(**checks):
    return Case(id="c", prompt="satu ditambah satu", checks=Checks(**checks))


class FakeAgent:
    def __init__(self, messages=None, exc=None):
        self.messages, self.exc, self.seen = messages, exc, None

    def invoke(self, payload, config):
        self.seen = (payload, config)
        if self.exc:
            raise self.exc
        return {"messages": self.messages}


def good_messages():
    call = {"name": "add_numbers", "args": {"numbers": [1, 1]}, "id": "c0"}
    return [
        HumanMessage("satu ditambah satu"),
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content='{"result": 2.0}', name="add_numbers", tool_call_id="c0"),
        AIMessage("Hasilnya adalah 2."),
    ]


def test_run_case_once_passes_and_sends_the_prompt_and_limit():
    agent = FakeAgent(good_messages())
    assert support.run_case_once(case(expect_tools=["add_numbers"], answer_contains_any=["2"]), agent, 7) == []
    payload, config = agent.seen
    assert payload == {"messages": [("human", "satu ditambah satu")]} and config == {"recursion_limit": 7}


def test_run_case_once_reports_failed_checks():
    out = support.run_case_once(case(answer_contains_any=["99"]), FakeAgent(good_messages()), 7)
    assert len(out) == 1 and "answer_contains_any" in out[0]


def test_run_case_once_turns_agent_errors_into_a_failed_repeat():
    out = support.run_case_once(case(expect_tools=["add_numbers"]), FakeAgent(exc=RuntimeError("boom")), 7)
    assert out == ["error: RuntimeError: boom"]


# --- the report is written when cases ran, also when some failed


def test_finish_session_writes_a_report_for_a_failing_run(tmp_path):
    import json

    from tests.evals.scoring import score_case

    results = [score_case("add", [[], []], 1.0), score_case("sub", [["tool_args: wrong order"], []], 1.0)]
    options = support.EvalOptions(repeats=2, min_pass_rate=1.0, model="x/y")
    path = support.finish_session(results, Settings(_env_file=None, git_sha="abc"), options, tmp_path)
    data = json.loads(path.read_text())
    assert data["passed"] is False and data["model"] == "x/y" and data["commit"] == "abc"
    assert [c["id"] for c in data["cases"]] == ["add", "sub"]


def test_finish_session_writes_nothing_when_no_case_ran(tmp_path):
    options = support.EvalOptions(repeats=3, min_pass_rate=1.0, model=None)
    assert support.finish_session([], Settings(_env_file=None), options, tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_options_are_validated():
    class Config:
        def __init__(self, repeats, rate, model=None):
            self.values = {"--eval-repeats": repeats, "--eval-min-pass-rate": rate, "--eval-model": model}

        def getoption(self, name):
            return self.values[name]

    assert support.eval_options_from(Config(3, 1.0)) == support.EvalOptions(3, 1.0, None)
    for bad in (Config(0, 1.0), Config(3, 0), Config(3, 1.5)):
        with pytest.raises(pytest.UsageError):
            support.eval_options_from(bad)
