from tests.fakes import NoStateAgent, use_agent


def assert_envelope(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response.headers["x-request-id"]
    return error


def test_unknown_agent(client):
    r = client.post("/agents/nope", json={"prompt": "x"})
    assert_envelope(r, 404, "agent_not_found")


def test_unknown_route(client):
    assert_envelope(client.get("/does-not-exist"), 404, "not_found")


def test_wrong_method(client):
    assert_envelope(client.get("/chat"), 405, "method_not_allowed")


def test_validation_failure(client):
    r = client.post("/chat", json={"prompt": ""})
    error = assert_envelope(r, 422, "invalid_request")
    assert "prompt" in error["message"]


def test_request_id_from_caller_is_echoed(client):
    r = client.post("/agents/nope", json={"prompt": "x"}, headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert r.json()["error"]["request_id"] == "abc123"


class Boom(NoStateAgent):
    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("boom-secret-detail")


def test_unexpected_error_is_safe_and_traceable(client, caplog):
    import logging

    use_agent(client, Boom())
    with caplog.at_level(logging.ERROR, logger="agent_wf.api"):
        r = client.post("/agents/math", json={"prompt": "x", "thread_id": "t-500"})
    error = assert_envelope(r, 500, "internal_error")
    assert "boom-secret-detail" not in r.text
    assert "Traceback" not in r.text
    record = next(rec for rec in caplog.records if "unhandled error" in rec.getMessage())
    assert record.exc_info and "boom-secret-detail" in str(record.exc_info[1])
    assert record.request_id == error["request_id"]
    assert record.thread_id == "t-500"
