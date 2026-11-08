from agent_wf.config import get_settings
from tests.conftest import TEST_API_KEY

BODY = {"prompt": "x"}


def set_keys(monkeypatch, value):
    monkeypatch.setenv("API_KEYS", value)
    get_settings.cache_clear()


def test_missing_key_is_rejected(anon_client):
    for path in ("/chat", "/agents/math"):
        r = anon_client.post(path, json=BODY)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"


def test_wrong_key_is_rejected(anon_client):
    r = anon_client.post("/chat", json=BODY, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_valid_key_is_accepted(anon_client):
    r = anon_client.post("/chat", json=BODY, headers={"X-API-Key": TEST_API_KEY})
    assert r.status_code == 200


def test_either_of_two_keys_works(anon_client, monkeypatch):
    set_keys(monkeypatch, "old-key,new-key")
    for key in ("old-key", "new-key"):
        assert anon_client.post("/chat", json=BODY, headers={"X-API-Key": key}).status_code == 200


def test_removed_key_is_rejected(anon_client, monkeypatch):
    set_keys(monkeypatch, "new-key")
    assert anon_client.post("/chat", json=BODY, headers={"X-API-Key": "old-key"}).status_code == 401
    assert anon_client.post("/chat", json=BODY, headers={"X-API-Key": "new-key"}).status_code == 200


def test_liveness_is_open(anon_client):
    r = anon_client.get("/")
    assert r.status_code == 200 and r.json()["status"] == "healthy"


def test_auth_is_checked_before_validation(anon_client):
    r = anon_client.post("/chat", json={"prompt": ""})
    assert r.status_code == 401


def test_keys_never_leak_into_logs_or_responses(anon_client, monkeypatch, caplog):
    import logging

    set_keys(monkeypatch, "configured-secret-1,configured-secret-2")
    with caplog.at_level(logging.DEBUG):
        r = anon_client.post("/chat", json=BODY, headers={"X-API-Key": "submitted-wrong-key"})
    assert r.status_code == 401
    everything = r.text + caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    for secret in ("submitted-wrong-key", "configured-secret-1", "configured-secret-2"):
        assert secret not in everything


def test_rejection_log_has_request_id_and_path_only(anon_client, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="agent_wf.api"):
        r = anon_client.post("/chat", json=BODY, headers={"x-request-id": "rid-77"})
    record = next(rec for rec in caplog.records if "auth rejected" in rec.getMessage())
    assert record.getMessage() == "auth rejected: POST /chat"
    assert record.request_id == "rid-77"
    assert r.headers["x-request-id"] == "rid-77"


def test_auth_can_be_disabled_explicitly(anon_client, monkeypatch):
    monkeypatch.setenv("API_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    assert anon_client.post("/chat", json=BODY).status_code == 200
    assert anon_client.post("/agents/math", json=BODY).status_code == 200
