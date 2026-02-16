import pytest

from cannibal_core.config import Settings


def test_settings_default_provider_is_ollama() -> None:
    settings = Settings(telethon_api_id=1, telethon_api_hash="hash")
    assert settings.llm_provider == "ollama"


def test_openai_requires_key() -> None:
    with pytest.raises(ValueError):
        Settings(telethon_api_id=1, telethon_api_hash="hash", llm_provider="openai")


def test_ollama_requires_models() -> None:
    with pytest.raises(ValueError):
        Settings(
            telethon_api_id=1,
            telethon_api_hash="hash",
            llm_provider="ollama",
            ollama_model="",
        )
