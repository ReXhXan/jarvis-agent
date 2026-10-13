"""Central configuration, loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "mock"
    llm_model: str = "llama3.1"
    openai_api_key: str = ""
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    max_tool_steps: int = 5
    memory_window: int = 12
    data_dir: str = "./data"
    file_search_roots: str = "."
    allow_network: bool = True
    voice_enabled: bool = False
    log_level: str = "INFO"

    @property
    def roots(self) -> list[str]:
        return [r.strip() for r in self.file_search_roots.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
