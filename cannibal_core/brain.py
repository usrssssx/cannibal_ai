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

    async def generate(self, text: str, style_profile: str | None = None) -> str:
        logger.info("Generating rewritten post")
        examples = (
            self._settings.style_examples_ru
            if self._is_cyrillic(text)
            else self._settings.style_examples_en
        )
        return await self._llm_client.rewrite(text, examples, style_profile)
