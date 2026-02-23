from __future__ import annotations

from loguru import logger

from .config import Settings
from .llm_client import LLMClient


class Brain:
    def __init__(self, llm_client: LLMClient, settings: Settings) -> None:
        self._llm_client = llm_client
        self._settings = settings

    @staticmethod
    def _is_cyrillic(text: str) -> bool:
        for ch in text:
            ch_lower = ch.lower()
            if "а" <= ch_lower <= "я":
                return True
        return False

    @staticmethod
    def _detect_voice(text: str) -> str | None:
        lowered = text.lower()
        first_person = (" я ", " мне ", " меня ", " мной ", " мы ", " нас ", " нами ", " мой ", " моя ", " мои ")
        third_person = (" он ", " она ", " они ", " его ", " ее ", " их ")
        if any(token in f" {lowered} " for token in first_person):
            return "first_person"
        if any(token in f" {lowered} " for token in third_person):
            return "third_person"
        return None

    async def generate(
        self,
        text: str,
        style_profile: str | None = None,
        style_examples: list[str] | None = None,
    ) -> str:
        logger.info("Generating rewritten post")
        voice_hint = self._detect_voice(text)
        if style_examples:
            examples = style_examples
        else:
            examples = (
                self._settings.style_examples_ru
                if self._is_cyrillic(text)
                else self._settings.style_examples_en
            )
        return await self._llm_client.rewrite(
            text,
            examples,
            style_profile,
            voice_hint=voice_hint,
        )
