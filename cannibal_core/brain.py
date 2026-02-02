from __future__ import annotations

from loguru import logger

from .llm_client import LLMClient

STYLE_EXAMPLES = [
    "Market wrap: risk assets pushed higher as traders priced in a softer policy outlook.",
    "Quick take: the numbers look better than expected, but guidance remains cautious.",
    "Focus: liquidity is tightening, so short-term rallies may fade without confirmation.",
    "Update: the move was sharp, yet follow-through stays limited across majors.",
]


class Brain:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def generate(self, text: str) -> str:
        logger.info("Generating rewritten post")
        return await self._llm_client.rewrite(text, STYLE_EXAMPLES)
