from __future__ import annotations

import asyncio
import sys

from loguru import logger

from .brain import Brain
from .config import get_settings
from .database import init_db
from .deduplicator import Deduplicator
from .listener import Listener
from .llm_client import LLMClient
from .processor import Processor
from .vector_store import VectorStore


async def main() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    await init_db()

    llm_client = LLMClient(settings)
    vector_store = VectorStore(settings)
    deduplicator = Deduplicator(
        llm_client=llm_client,
        vector_store=vector_store,
        threshold=settings.duplicate_threshold,
    )
    brain = Brain(llm_client)
    processor = Processor(settings, deduplicator, brain, vector_store)
    listener = Listener(settings, processor)

    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
