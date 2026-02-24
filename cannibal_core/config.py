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
    bot_session: str = "cannibal_bot"
    webapp_user_session: str = "cannibal_webapp_userbot"
    target_channels: list[str] = Field(default_factory=list)

    llm_provider: str = "ollama"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_temperature: float = 0.4
    ollama_num_ctx: int | None = None
    ollama_num_predict: int | None = None
    ollama_top_p: float | None = None
    ollama_top_k: int | None = None
    ollama_repeat_penalty: float | None = None
    ollama_repeat_last_n: int | None = None
    ollama_mirostat: int | None = None
    ollama_mirostat_tau: float | None = None
    ollama_mirostat_eta: float | None = None
    ollama_num_thread: int | None = None

    image_enabled: bool = False
    image_search_provider: str = "pexels"
    image_generation_provider: str = "replicate"
    image_safe_only: bool = True
    image_download: bool = True
    image_output_dir: str = "./images"
    image_query_max_words: int = 12
    image_prompt_style: str = (
        "photojournalistic, realistic, natural lighting, high detail, no text"
    )

    pexels_api_key: str | None = None
    pexels_per_page: int = 1
    pexels_orientation: str = "landscape"

    replicate_api_token: str | None = None
    replicate_model_version: str | None = None
    replicate_poll_interval: float = 1.5
    replicate_timeout: float = 60.0
    replicate_negative_prompt: str | None = "nsfw, nude, nudity, gore, violence, text"

    sqlite_path: str = "./cannibal.db"
    chroma_persist_dir: str = "./chroma"
    chroma_collection: str = "cannibal_posts"
    output_path: str = "./output.txt"

    duplicate_threshold: float = 0.85

    processor_workers: int = 4
    processor_queue_size: int = 1000
    max_chars: int = 8000
    embedding_max_chars: int = 2000
    style_profile_posts: int = 80
    style_profile_examples: int = 4
    style_profile_example_limit: int = 200
    style_profile_example_min_chars: int = 40
    style_profile_example_max_chars: int = 400
    rewrite_mode: str = "balanced"
    rewrite_temperature: float = 0.4

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
    log_file: str | None = None
    log_rotation: str = "10 MB"
    log_retention: str = "14 days"
    admin_token: str | None = None
    data_retention_days: int = 90
    runs_retention_days: int | None = None
    logs_cleanup_days: int = 30

    bot_token: str | None = None
    bot_allowed_users: list[int] = Field(default_factory=list)
    bot_style_limit: int = 120
    bot_source_limit: int = 1
    bot_guide_url: str | None = None
    bot_user_session: str = "cannibal_bot_userbot"
    enforce_allowed_users: bool = True

    webapp_url: str | None = None
    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8000
    webapp_max_age_sec: int = 86400
    webapp_duplicate_to_chat: bool = True
    cloudflared_tunnel_token: str | None = None

    telegram_retry_attempts: int = 3
    telegram_retry_base_delay: float = 1.0
    telegram_flood_sleep_max: int = 120

    alert_bot_token: str | None = None
    alert_chat_id: int | None = None

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

    @field_validator("bot_allowed_users", mode="before")
    @classmethod
    def _parse_allowed_users(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return [int(part) for part in parts]
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return [int(part) for part in value]
        return value

    @field_validator("alert_chat_id", mode="before")
    @classmethod
    def _parse_alert_chat_id(cls, value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    @field_validator("style_examples_ru", "style_examples_en", mode="before")
    @classmethod
    def _parse_style_examples(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split("||") if part.strip()]
        return value

    @field_validator("rewrite_mode", mode="before")
    @classmethod
    def _parse_rewrite_mode(cls, value):
        if value is None:
            return "balanced"
        if isinstance(value, str):
            return value.strip().lower()
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
        if self.image_enabled:
            if self.image_search_provider.lower().strip() != "pexels":
                raise ValueError("IMAGE_SEARCH_PROVIDER must be 'pexels'")
            if not self.pexels_api_key:
                raise ValueError("PEXELS_API_KEY is required when IMAGE_ENABLED=true")
            if self.image_generation_provider.lower().strip() != "replicate":
                raise ValueError("IMAGE_GENERATION_PROVIDER must be 'replicate'")
            if not self.replicate_api_token:
                raise ValueError("REPLICATE_API_TOKEN is required when IMAGE_ENABLED=true")
            if not self.replicate_model_version:
                raise ValueError(
                    "REPLICATE_MODEL_VERSION is required when IMAGE_ENABLED=true"
                )
        if self.rewrite_mode not in {"balanced", "aggressive"}:
            raise ValueError("REWRITE_MODE must be 'balanced' or 'aggressive'")
        return self

    @property
    def sqlite_url(self) -> str:
        path = Path(self.sqlite_path)
        if path.is_absolute():
            return f"sqlite+aiosqlite:////{path.as_posix().lstrip('/')}"
        return f"sqlite+aiosqlite:///{path.as_posix()}"

    @property
    def sqlite_sync_url(self) -> str:
        path = Path(self.sqlite_path)
        if path.is_absolute():
            return f"sqlite:////{path.as_posix().lstrip('/')}"
        return f"sqlite:///{path.as_posix()}"

    @property
    def ollama_chat_options(self) -> dict[str, int | float]:
        options: dict[str, int | float] = {
            "temperature": self.ollama_temperature,
        }
        if self.ollama_num_ctx is not None:
            options["num_ctx"] = self.ollama_num_ctx
        if self.ollama_num_predict is not None:
            options["num_predict"] = self.ollama_num_predict
        if self.ollama_top_p is not None:
            options["top_p"] = self.ollama_top_p
        if self.ollama_top_k is not None:
            options["top_k"] = self.ollama_top_k
        if self.ollama_repeat_penalty is not None:
            options["repeat_penalty"] = self.ollama_repeat_penalty
        if self.ollama_repeat_last_n is not None:
            options["repeat_last_n"] = self.ollama_repeat_last_n
        if self.ollama_mirostat is not None:
            options["mirostat"] = self.ollama_mirostat
        if self.ollama_mirostat_tau is not None:
            options["mirostat_tau"] = self.ollama_mirostat_tau
        if self.ollama_mirostat_eta is not None:
            options["mirostat_eta"] = self.ollama_mirostat_eta
        if self.ollama_num_thread is not None:
            options["num_thread"] = self.ollama_num_thread
        return options


def get_settings() -> Settings:
    return Settings()
