from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    telethon_api_id: int
    telethon_api_hash: str
    telethon_session: str = "cannibal_userbot"
    target_channels: list[str] = Field(default_factory=list)

    llm_provider: str = "openai"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"

    sqlite_path: str = "./cannibal.db"
    chroma_persist_dir: str = "./chroma"
    chroma_collection: str = "cannibal_posts"

    duplicate_threshold: float = 0.85

    processor_workers: int = 4
    processor_queue_size: int = 1000
    max_chars: int = 8000

    style_examples_ru: list[str] = Field(
        default_factory=lambda: [
            "Кратко: рынок отыгрывает позитив, но уверенности пока мало.",
            "Факт: цифры лучше ожиданий, но прогноз остаётся осторожным.",
            "Фокус: ликвидность сжимается, поэтому росту нужен подтверждающий объём.",
            "Апдейт: импульс был сильным, но продолжение пока ограничено.",
        ]
    )
    style_examples_en: list[str] = Field(
        default_factory=lambda: [
            "Market wrap: risk assets pushed higher as traders priced in a softer policy outlook.",
            "Quick take: the numbers look better than expected, but guidance remains cautious.",
            "Focus: liquidity is tightening, so short-term rallies may fade without confirmation.",
            "Update: the move was sharp, yet follow-through stays limited across majors.",
        ]
    )

    ad_stop_words: list[str] = Field(
        default_factory=lambda: [
            "подписывайтесь",
            "розыгрыш",
            "промокод",
            "скидка",
            "реклама",
        ]
    )

    log_level: str = "INFO"

    @field_validator("target_channels", mode="before")
    @classmethod
    def _parse_channels(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("ad_stop_words", mode="before")
    @classmethod
    def _parse_stop_words(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("style_examples_ru", "style_examples_en", mode="before")
    @classmethod
    def _parse_style_examples(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split("||") if part.strip()]
        return value

    @model_validator(mode="after")
    def _validate_provider(self):
        provider = self.llm_provider.lower().strip()
        if provider not in {"openai", "ollama"}:
            raise ValueError("LLM_PROVIDER must be 'openai' or 'ollama'")
        if provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return self

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path)
        if path.is_absolute():
            return f"sqlite+aiosqlite:////{path.as_posix().lstrip('/')}"
        return f"sqlite+aiosqlite:///{path.as_posix()}"


def get_settings() -> Settings:
    return Settings()
