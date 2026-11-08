import asyncio

from agent_wf.config import get_settings
from tests.fakes import NoStateAgent, use_agent


class SlowAgent(NoStateAgent):
    def __init__(self):
        self.cancelled = False

    async def ainvoke(self, payload, config=None):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_run_over_budget_is_cancelled_and_reported_as_504(client, monkeypatch):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    slow = SlowAgent()
    use_agent(client, slow)
    r = client.post("/agents/math", json={"prompt": "x"})
    assert r.status_code == 504
    error = r.json()["error"]
    assert error["code"] == "agent_timeout"
    assert error["request_id"] == r.headers["x-request-id"]
    assert slow.cancelled


def test_run_within_budget_is_unaffected(client):
    assert client.post("/agents/math", json={"prompt": "x"}).status_code == 200


def test_unrelated_timeout_inside_the_run_is_not_reported_as_budget(client):
    class Raises(NoStateAgent):
        async def ainvoke(self, payload, config=None):
            raise TimeoutError("some inner timeout")

    use_agent(client, Raises())
    r = client.post("/agents/math", json={"prompt": "x"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
