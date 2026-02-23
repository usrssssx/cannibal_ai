from __future__ import annotations

import asyncio

from .alerts import send_alert_sync
from .brain import Brain
from .config import get_settings
from .database import init_db, init_engine
from .deduplicator import Deduplicator
from .image_client import ImageClient
from .listener import Listener
from .llm_client import LLMClient
from .logging_setup import configure_logging
from .processor import Processor
from .style_profile import build_style_examples, build_style_profiles
from .vector_store import VectorStore


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    init_engine(settings)
    await init_db()

    llm_client = LLMClient(settings)
    await llm_client.health_check()
    vector_store = VectorStore(settings)
    deduplicator = Deduplicator(
        llm_client=llm_client,
        vector_store=vector_store,
        threshold=settings.duplicate_threshold,
    )
    brain = Brain(llm_client, settings)
    style_profiles = await build_style_profiles(
        limit=settings.style_profile_posts,
    )
    style_examples = await build_style_examples(
        limit=settings.style_profile_example_limit,
        max_examples=settings.style_profile_examples,
        min_chars=settings.style_profile_example_min_chars,
        max_chars=settings.style_profile_example_max_chars,
    )
    image_client = ImageClient(settings) if settings.image_enabled else None
    processor = Processor(
        settings,
        deduplicator,
        brain,
        vector_store,
        style_profiles,
        image_client=image_client,
        style_examples=style_examples,
    )
    await processor.start()
    listener = Listener(settings, processor)

    await listener.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        try:
            settings = get_settings()
            send_alert_sync(settings, "cannibal_core.main", repr(exc))
        except Exception:
            pass
        raise
