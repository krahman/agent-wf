import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent_wf.tools.math_tools import all_tools

load_dotenv()

SYSTEM_PROMPT = (
    "You are a helpful assistant that can perform various mathematical operations and look up "
    "information. Use the tools precisely and explain your reasoning clearly."
)


def build_agent(model: str = "openai/gpt-4o"):
    llm = ChatOpenAI(
        model=model,
        base_url=os.getenv("OPENROUTER_BASE_URL"),
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
    )
    return create_agent(model=llm, tools=all_tools, system_prompt=SYSTEM_PROMPT)
