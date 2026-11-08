from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def fake_llm(text: str = "hi", n: int = 50) -> FakeLLM:
    return FakeLLM(messages=iter([AIMessage(text)] * n))


class NoStateAgent:
    """Base for hand-written fake agents: no stored conversation, so there is nothing to repair."""

    async def aget_state(self, config):
        return SimpleNamespace(values={})


def use_agent(client, agent, name: str = "math"):
    """Install a fake agent for both kinds of request: with a thread_id and without one."""
    client.app.state.agents[name] = agent
    client.app.state.stateless_agents[name] = agent
