import os
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str | None = None
    llm_model: str = os.getenv("OPENAPI_MODEL", "openai/gpt-4o")
    llm_timeout: float = 60.0
    agent_recursion_limit: int = 15
    log_level: str = "INFO"

    langfuse_tracing: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
