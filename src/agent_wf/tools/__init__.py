from langchain_core.tools import BaseTool

from agent_wf.tools.math import math_tools
from agent_wf.tools.wikipedia import wikipedia_tools

TOOLSETS: dict[str, list[BaseTool]] = {
    "math": math_tools,
    "wikipedia": wikipedia_tools,
}


def get_tools(*toolsets: str) -> list[BaseTool]:
    return [tool for name in toolsets for tool in TOOLSETS[name]]
