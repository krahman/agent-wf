from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel

from agent_wf.llm import build_llm
from agent_wf.tools import get_tools


@dataclass(frozen=True)
class AgentSpec:
    name: str
    system_prompt: str
    toolsets: tuple[str, ...]
    model: str | None = None

    def build(self, llm: BaseChatModel | None = None, checkpointer=None):
        return create_agent(
            model=llm or build_llm(self.model),
            tools=get_tools(*self.toolsets),
            system_prompt=self.system_prompt,
            checkpointer=checkpointer,
        )
