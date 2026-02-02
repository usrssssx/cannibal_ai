from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
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

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    sqlite_path: str = "./cannibal.db"
    chroma_persist_dir: str = "./chroma"
    chroma_collection: str = "cannibal_posts"

    duplicate_threshold: float = 0.85

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

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path)
        if path.is_absolute():
            return f"sqlite+aiosqlite:////{path.as_posix().lstrip('/')}"
        return f"sqlite+aiosqlite:///{path.as_posix()}"


def get_settings() -> Settings:
    return Settings()
