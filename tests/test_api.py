from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import agent_wf.api.app as app_module


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def test_endpoints(monkeypatch):
    monkeypatch.setattr(
        app_module, "build_llm", lambda *a, **k: FakeLLM(messages=iter([AIMessage("hi")] * 10))
    )
    with TestClient(app_module.app) as client:
        assert client.get("/").json() == {"status": "healthy"}
        assert client.post("/chat", json={"prompt": "x"}).json() == {"statement": "hi"}
        assert client.post("/agents/math", json={"prompt": "x"}).json() == {"answer": "hi"}
        assert client.post("/agents/nope", json={"prompt": "x"}).status_code == 404
        assert client.post("/chat", json={"prompt": ""}).status_code == 422
