from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        protected_namespaces=("settings_",),
    )

    model_hf: str
    model_context_size: int
    admin_login: str
    admin_pass: str
    llama_host: str
    llama_port: int
    model_multimodal: bool = True
    max_queue_size: int = 3
    raw_messages_size: int = 10
    messages_summary_size: int = 5
    summary_tokens_size: int = 12000
    summary_model_hf: str | None = None
    summary_model_context_size: int | None = None
    use_dedicated_summary_model: bool = False
    summary_llama_host: str = "llama-summary"
    summary_llama_port: int = 8767
    database_url: str
    redis_url: str
    qdrant_url: str
    embedding_model: str
    log_level: str = "INFO"
    jwt_secret: str
    response_max_tokens: int = 3072

    @field_validator("raw_messages_size")
    @classmethod
    def validate_raw_messages_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("RAW_MESSAGES_SIZE must be >= 1")
        return value

    @field_validator("max_queue_size")
    @classmethod
    def validate_max_queue_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MAX_QUEUE_SIZE must be >= 1")
        return value

    @property
    def summary_enabled(self) -> bool:
        return self.messages_summary_size >= 1

    @property
    def llama_url(self) -> str:
        return f"http://{self.llama_host}:{self.llama_port}"

    @property
    def summary_llama_url(self) -> str:
        return f"http://{self.summary_llama_host}:{self.summary_llama_port}"

    @property
    def effective_summary_model(self) -> str:
        return self.summary_model_hf or self.model_hf

    @property
    def effective_summary_context(self) -> int:
        return self.summary_model_context_size or self.model_context_size

    @property
    def summary_llama_endpoint(self) -> str:
        if self.use_dedicated_summary_model:
            return self.summary_llama_url
        return self.llama_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
