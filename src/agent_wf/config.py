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
    git_sha: str = "unknown"  # injected at image build time

    api_auth_enabled: bool = True
    api_keys: SecretStr | None = None  # comma-separated; several keys allow rotation
    wikipedia_contact: str = "https://github.com/krahman/agent-wf"  # sent in the User-Agent
    max_prompt_chars: int = 4000
    agent_timeout_seconds: float = 90.0

    langfuse_tracing: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "http://localhost:3000"

    def api_key_list(self) -> list[str]:
        if self.api_keys is None:
            return []
        return [k.strip() for k in self.api_keys.get_secret_value().split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
