from pydantic import BaseModel, Field, field_validator

from agent_wf.config import get_settings


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def _within_length_limit(cls, value: str) -> str:
        limit = get_settings().max_prompt_chars
        if len(value) > limit:
            raise ValueError(f"must be at most {limit} characters")
        return value


class AgentRequest(ChatRequest):
    thread_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ChatResponse(BaseModel):
    statement: str


class AgentResponse(BaseModel):
    answer: str
