from agent_wf import __version__


def test_endpoints(client):
    assert client.get("/").json()["status"] == "healthy"
    assert client.post("/chat", json={"prompt": "x"}).json() == {"statement": "hi"}
    assert client.post("/agents/math", json={"prompt": "x"}).json() == {"answer": "hi"}
    assert client.post("/agents/nope", json={"prompt": "x"}).status_code == 404
    assert client.post("/chat", json={"prompt": ""}).status_code == 422


def test_version_exposed(client):
    assert client.app.version == __version__ != "0.0.0+unknown"
    body = client.get("/").json()
    assert body["version"] == __version__ and "commit" in body
