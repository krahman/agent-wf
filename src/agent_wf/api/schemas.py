from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)


class AgentRequest(ChatRequest):
    thread_id: str | None = None


class ChatResponse(BaseModel):
    statement: str


class AgentResponse(BaseModel):
    answer: str
