from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .brain import Brain
from .config import Settings
from .database import Channel, Post, get_session
from .deduplicator import Deduplicator
from .vector_store import VectorStore


class Processor:
    def __init__(
        self,
        settings: Settings,
        deduplicator: Deduplicator,
        brain: Brain,
        vector_store: VectorStore,
    ) -> None:
        self._settings = settings
        self._deduplicator = deduplicator
        self._brain = brain
        self._vector_store = vector_store

    async def handle_message(
        self,
        channel_name: str,
        channel_id: int | None,
        message_id: int,
        text: str,
    ) -> None:
        logger.info("New post detected from {}", channel_name)
        await self._store_raw_post(channel_name, channel_id, message_id, text)

        dedup = await self._deduplicator.check(text)
        if dedup.is_duplicate:
            logger.info("Skipping duplicate post")
            return

        doc_id = f"{channel_id or channel_name}:{message_id}"
        created_at = datetime.now(timezone.utc).timestamp()
        metadata = {
            "channel": channel_name,
            "message_id": message_id,
            "created_at": created_at,
        }
        await self._vector_store.add(doc_id, dedup.embedding, text, metadata)

        rewritten = await self._brain.generate(text)
        logger.info("Generated post:\n{}", rewritten)
        print(rewritten)

    async def _store_raw_post(
        self,
        channel_name: str,
        channel_id: int | None,
        message_id: int,
        text: str,
    ) -> None:
        async with get_session() as session:
            channel = await self._get_or_create_channel(
                session, channel_name, channel_id
            )
            post = Post(
                channel_id=channel.id,
                telegram_msg_id=message_id,
                text=text,
            )
            session.add(post)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.debug("Post already stored in database")

    async def _get_or_create_channel(
        self, session, channel_name: str, channel_id: int | None
    ) -> Channel:
        if channel_id is not None:
            stmt = select(Channel).where(Channel.telegram_id == channel_id)
        else:
            stmt = select(Channel).where(Channel.name == channel_name)
        result = await session.execute(stmt)
        channel = result.scalar_one_or_none()
        if channel:
            return channel

        channel = Channel(name=channel_name, telegram_id=channel_id)
        session.add(channel)
        await session.flush()
        return channel
