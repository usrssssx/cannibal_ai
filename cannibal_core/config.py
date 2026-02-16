from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource


class _LenientEnvSettingsSource(EnvSettingsSource):
    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except ValueError:
            return value


class _LenientDotEnvSettingsSource(DotEnvSettingsSource):
    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except ValueError:
            return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        config = settings_cls.model_config
        env = _LenientEnvSettingsSource(
            settings_cls,
            case_sensitive=config.get("case_sensitive"),
            env_prefix=config.get("env_prefix"),
            env_nested_delimiter=config.get("env_nested_delimiter"),
            env_nested_max_split=config.get("env_nested_max_split"),
            env_ignore_empty=config.get("env_ignore_empty"),
            env_parse_none_str=config.get("env_parse_none_str"),
            env_parse_enums=config.get("env_parse_enums"),
        )
        dotenv = _LenientDotEnvSettingsSource(
            settings_cls,
            env_file=config.get("env_file"),
            env_file_encoding=config.get("env_file_encoding"),
            case_sensitive=config.get("case_sensitive"),
            env_prefix=config.get("env_prefix"),
            env_nested_delimiter=config.get("env_nested_delimiter"),
            env_nested_max_split=config.get("env_nested_max_split"),
            env_ignore_empty=config.get("env_ignore_empty"),
            env_parse_none_str=config.get("env_parse_none_str"),
            env_parse_enums=config.get("env_parse_enums"),
        )
        return (
            init_settings,
            env,
            dotenv,
            file_secret_settings,
        )

    telethon_api_id: int
    telethon_api_hash: str
    telethon_session: str = "cannibal_userbot"
    target_channels: list[str] = Field(default_factory=list)

    llm_provider: str = "ollama"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"

    sqlite_path: str = "./cannibal.db"
    chroma_persist_dir: str = "./chroma"
    chroma_collection: str = "cannibal_posts"
    output_path: str = "./output.txt"

    duplicate_threshold: float = 0.85

    processor_workers: int = 4
    processor_queue_size: int = 1000
    max_chars: int = 8000
    style_profile_posts: int = 80

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
        if provider == "ollama":
            if not self.ollama_base_url:
                raise ValueError("OLLAMA_BASE_URL is required when LLM_PROVIDER=ollama")
            if not self.ollama_model:
                raise ValueError("OLLAMA_MODEL is required when LLM_PROVIDER=ollama")
            if not self.ollama_embedding_model:
                raise ValueError(
                    "OLLAMA_EMBEDDING_MODEL is required when LLM_PROVIDER=ollama"
                )
        return self

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path)
        if path.is_absolute():
            return f"sqlite+aiosqlite:////{path.as_posix().lstrip('/')}"
        return f"sqlite+aiosqlite:///{path.as_posix()}"


def get_settings() -> Settings:
    return Settings()
