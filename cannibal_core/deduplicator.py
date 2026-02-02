from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from loguru import logger

from .llm_client import LLMClient
from .vector_store import VectorStore


@dataclass(slots=True)
class DedupResult:
    is_duplicate: bool
    similarity: float | None
    matched_id: str | None
    embedding: list[float]


class Deduplicator:
    def __init__(self, llm_client: LLMClient, vector_store: VectorStore, threshold: float) -> None:
        self._llm_client = llm_client
        self._vector_store = vector_store
        self._threshold = threshold

    async def check(self, text: str) -> DedupResult:
        embedding = await self._llm_client.embed(text)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self._vector_store.query_similar(embedding, since)

        distances = result.get("distances", [[]])
        ids = result.get("ids", [[]])

        best_similarity = None
        matched_id = None

        if distances and distances[0]:
            best_distance = distances[0][0]
            best_similarity = 1 - best_distance
            matched_id = ids[0][0] if ids and ids[0] else None

        is_duplicate = (
            best_similarity is not None and best_similarity >= self._threshold
        )

        if is_duplicate:
            logger.info(
                "Duplicate detected (similarity={}).", round(best_similarity, 3)
            )
        else:
            logger.info("Post is unique.")

        return DedupResult(
            is_duplicate=is_duplicate,
            similarity=best_similarity,
            matched_id=matched_id,
            embedding=embedding,
        )
