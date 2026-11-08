from langchain_openai import ChatOpenAI

from agent_wf.config import Settings, get_settings


def build_llm(model: str | None = None, settings: Settings | None = None) -> ChatOpenAI:
    settings = settings or get_settings()
    if settings.openrouter_api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return ChatOpenAI(
        model=model or settings.llm_model,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        timeout=settings.llm_timeout,
    )
