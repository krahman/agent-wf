"""Per-repeat traces and scores, against a fake Langfuse: names, tags, session, score payloads, isolation."""

import logging
from contextlib import contextmanager

import httpx
import pytest
from langchain_core.messages import AIMessage

from agent_wf.config import Settings
from tests.evals import support, tracing
from tests.evals.cases import Case
from tests.evals.harness import Checks

RUN_ID = "20261108T094612Z-openai-gpt-4o"
HOST = "http://lf.test:3000"
PUBLIC, SECRET = "pk-lf-test", "sk-lf-very-secret-value"


class FakeHandler:
    def __init__(self, trace_id="trace-1"):
        self.last_trace_id = trace_id


class FakeLangfuse:
    """Stands in for what the tracer touches: the SDK's attribute context and handler, and the score POST."""

    def __init__(self, monkeypatch, trace_id="trace-1", status=200):
        self.attributes, self.posts, self.handler = [], [], FakeHandler(trace_id)

        @contextmanager
        def propagate_attributes(**kwargs):
            self.attributes.append(kwargs)
            yield

        def post(url, **kwargs):
            self.posts.append({"url": url, **kwargs})
            return httpx.Response(status, request=httpx.Request("POST", url))

        monkeypatch.setattr(tracing, "propagate_attributes", propagate_attributes)
        monkeypatch.setattr(tracing, "trace_callbacks", lambda: [self.handler])
        monkeypatch.setattr(tracing.httpx, "post", post)

    @property
    def bodies(self):
        return [p["json"] for p in self.posts]


class FakeAgent:
    def __init__(self, answer="It is 2."):
        self.answer, self.configs = answer, []

    def invoke(self, payload, config):
        self.configs.append(config)
        return {"messages": [AIMessage(self.answer)]}


def case(**checks):
    return Case(id="add-basic", prompt="1+1", checks=Checks(**checks))


def tracer(model="openai/gpt-4o"):
    return tracing.Tracer(RUN_ID, model, HOST, PUBLIC, SECRET)


PASSING = {"answer_number": [{"value": 2}]}
FAILING = {"answer_number": [{"value": 99}]}


# --- one trace per repeat, named and grouped


def test_each_repeat_is_named_grouped_and_tagged(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    support.run_repeat(case(**PASSING), FakeAgent(), 15, repeat=2, tracer=tracer())
    [attrs] = fake.attributes
    assert attrs["trace_name"] == "eval:add-basic"
    assert attrs["session_id"] == RUN_ID
    assert attrs["tags"] == ["eval", "case:add-basic", "repeat:2", "model:openai/gpt-4o"]
    assert attrs["metadata"] == {"eval_case": "add-basic", "repeat": "2", "model": "openai/gpt-4o"}


def test_the_agent_gets_the_tracing_callbacks_and_the_recursion_limit(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    agent = FakeAgent()
    support.run_repeat(case(**PASSING), agent, 7, repeat=1, tracer=tracer())
    [config] = agent.configs
    assert config["recursion_limit"] == 7 and config["callbacks"] == [fake.handler]


def test_the_trace_id_comes_back_for_the_report(monkeypatch):
    FakeLangfuse(monkeypatch, trace_id="abc123")
    failures, trace_id = support.run_repeat(case(**PASSING), FakeAgent(), 15, 1, tracer())
    assert failures == [] and trace_id == "abc123"


# --- the score: a boolean eval_pass on the repeat's trace, through Langfuse's REST API


def test_a_passing_repeat_posts_a_true_score_without_a_comment(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    support.run_repeat(case(**PASSING), FakeAgent(), 15, 1, tracer())
    [post] = fake.posts
    assert post["url"] == f"{HOST}/api/public/scores"
    assert post["json"] == {"name": "eval_pass", "value": 1, "dataType": "BOOLEAN", "traceId": "trace-1"}
    assert post["auth"] == (PUBLIC, SECRET) and post["timeout"] == 3


def test_a_failing_repeat_posts_a_false_score_with_the_failed_checks_as_the_comment(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    failures, _ = support.run_repeat(case(**FAILING), FakeAgent(), 15, 1, tracer())
    [body] = fake.bodies
    assert body["value"] == 0 and body["dataType"] == "BOOLEAN" and body["traceId"] == "trace-1"
    assert body["comment"] == failures[0] and "answer_number: expected 99" in body["comment"]


def test_several_failures_are_joined_and_a_long_comment_is_cut_to_500(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    t, trace = tracer(), tracing.RepeatTrace(callbacks=[], trace_id="t")
    t.score(trace, ["first failure", "second failure"])
    t.score(trace, ["x" * 2000])
    assert fake.bodies[0]["comment"] == "first failure | second failure"
    assert len(fake.bodies[1]["comment"]) == 500


def test_no_trace_id_means_no_score(monkeypatch):
    fake = FakeLangfuse(monkeypatch, trace_id=None)
    failures, trace_id = support.run_repeat(case(**PASSING), FakeAgent(), 15, 1, tracer())
    assert failures == [] and trace_id is None and fake.posts == []


def test_a_trailing_slash_in_the_host_does_not_double_up(monkeypatch):
    fake = FakeLangfuse(monkeypatch)
    tracing.Tracer(RUN_ID, "m", HOST + "/", PUBLIC, SECRET).score(tracing.RepeatTrace([], "t"), [])
    assert fake.posts[0]["url"] == f"{HOST}/api/public/scores"


# --- untraced runs touch nothing


def test_an_untraced_run_makes_no_langfuse_call(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Langfuse used without --eval-trace")

    monkeypatch.setattr(tracing, "propagate_attributes", forbidden)
    monkeypatch.setattr(tracing, "trace_callbacks", forbidden)
    monkeypatch.setattr(tracing.httpx, "post", forbidden)
    agent = FakeAgent()
    failures, trace_id = support.run_repeat(case(**PASSING), agent, 15, 1, tracer=None)
    assert failures == [] and trace_id is None
    assert agent.configs == [{"recursion_limit": 15}], "no callbacks without tracing"


# --- tracing can never change a result


@pytest.mark.parametrize("broken", ["post_raises", "post_500", "post_400", "attributes", "callbacks", "trace_id"])
@pytest.mark.parametrize(("checks", "expect_failures"), [(PASSING, False), (FAILING, True)])
def test_a_langfuse_failure_never_changes_pass_or_fail(monkeypatch, broken, checks, expect_failures):
    fake = FakeLangfuse(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("langfuse is down")

    if broken == "post_raises":
        monkeypatch.setattr(tracing.httpx, "post", boom)
    elif broken in ("post_500", "post_400"):
        status = int(broken.removeprefix("post_"))
        monkeypatch.setattr(
            tracing.httpx, "post", lambda url, **kw: httpx.Response(status, request=httpx.Request("POST", url))
        )
    elif broken == "trace_id":
        fake.handler = type("H", (), {"last_trace_id": property(boom)})()
        monkeypatch.setattr(tracing, "trace_callbacks", lambda: [fake.handler])
    else:
        monkeypatch.setattr(tracing, {"attributes": "propagate_attributes", "callbacks": "trace_callbacks"}[broken], boom)
    failures, _ = support.run_repeat(case(**checks), FakeAgent(), 15, 1, tracer())
    assert bool(failures) is expect_failures


def test_after_the_first_failed_score_no_more_are_attempted_so_an_outage_costs_one_timeout(monkeypatch, caplog):
    fake = FakeLangfuse(monkeypatch)
    attempts = []

    def down(url, **kwargs):
        attempts.append(url)
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(tracing.httpx, "post", down)
    t = tracer()
    with caplog.at_level(logging.WARNING, logger="agent_wf.evals"):
        for _ in range(5):
            support.run_repeat(case(**PASSING), FakeAgent(), 15, 1, t)
    assert len(attempts) == 1
    assert sum("could not record eval_pass scores" in r.getMessage() for r in caplog.records) == 1
    assert fake.posts == []


def test_the_secret_key_never_reaches_logs_or_repr(monkeypatch, caplog):
    FakeLangfuse(monkeypatch)
    monkeypatch.setattr(tracing.httpx, "post", lambda url, **kw: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    t = tracer()
    with caplog.at_level(logging.DEBUG):
        support.run_repeat(case(**PASSING), FakeAgent(), 15, 1, t)
    assert SECRET not in caplog.text and SECRET not in repr(t) and PUBLIC not in repr(t)


def test_an_agent_error_is_a_failed_repeat_and_is_scored_false(monkeypatch):
    fake = FakeLangfuse(monkeypatch)

    class Crashing:
        def invoke(self, payload, config):
            raise RuntimeError("model unavailable")

    failures, _ = support.run_repeat(case(**PASSING), Crashing(), 15, 1, tracer())
    assert failures == ["error: RuntimeError: model unavailable"]
    assert fake.bodies[0]["value"] == 0 and "model unavailable" in fake.bodies[0]["comment"]


# --- building the tracer


def test_make_tracer_only_when_requested():
    settings = Settings(_env_file=None, langfuse_public_key=PUBLIC, langfuse_secret_key=SECRET, langfuse_host=HOST)
    assert tracing.make_tracer(False, RUN_ID, "m", settings) is None
    made = tracing.make_tracer(True, RUN_ID, "openai/gpt-4o", settings)
    assert (made.run_id, made.model, made.host) == (RUN_ID, "openai/gpt-4o", HOST)
    assert (made.public_key, made.secret_key) == (PUBLIC, SECRET)
    assert SECRET not in repr(made)
