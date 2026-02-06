from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import chromadb
from loguru import logger

from .config import Settings


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(
        self,
        doc_id: str,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        payload = {
            "ids": [doc_id],
            "embeddings": [embedding],
            "documents": [document],
            "metadatas": [metadata],
        }
        try:
            await asyncio.to_thread(self._collection.add, **payload)
            logger.debug("Vector stored: {}", doc_id)
        except Exception:
            logger.exception("Failed to store vector: {}", doc_id)

    async def query_similar(
        self,
        embedding: list[float],
        since: datetime,
        n_results: int = 5,
    ) -> dict[str, Any]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        else:
            since = since.astimezone(timezone.utc)
        since_ts = since.timestamp()

        def _query():
            return self._collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where={"created_at": {"$gte": since_ts}},
                include=["distances", "metadatas", "documents", "ids"],
            )

        try:
            result = await asyncio.to_thread(_query)
            return result
        except Exception:
            logger.exception("Vector query failed")
            return {"distances": [[]], "ids": [[]]}
