from fastapi import FastAPI
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from dotenv import load_dotenv
import os

from agent_wf.agents.math_agent import build_agent

load_dotenv()

app = FastAPI()

openai_client = OpenAI(
    base_url=os.getenv('OPENROUTER_BASE_URL'),
    api_key=os.getenv('OPENROUTER_API_KEY'),
)

@app.get("/")
def root_controller():
    return {"status": "healthy"}

@app.get("/chat")
def chat_controller(prompt: str = "inspire me"):
    messages = [
        ChatCompletionSystemMessageParam(role="system", content="You are a helpful assistant."),
        ChatCompletionUserMessageParam(role="user", content=prompt),
    ]
    model = os.getenv("OPENAPI_MODEL", "openai/gpt-4o")
    response = openai_client.chat.completions.create(
        model=model,
        messages=messages,
    )
    statement = response.choices[0].message.content
    return {"statement": statement}


math_agent = build_agent()

@app.get("/math-agent")
def math_agent_controller(prompt: str = "What is 25 divided by 4?"):
    result = math_agent.invoke({"messages": [("human", prompt)]})
    return {"answer": result["messages"][-1].content}
