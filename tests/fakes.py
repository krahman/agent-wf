from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def fake_llm(text: str = "hi", n: int = 50) -> FakeLLM:
    return FakeLLM(messages=iter([AIMessage(text)] * n))
