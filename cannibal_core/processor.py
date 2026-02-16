from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .brain import Brain
from .config import Settings
from .database import Channel, Post, get_session
from .deduplicator import Deduplicator
from .style_profile import StyleProfileCache
from .vector_store import VectorStore


class Processor:
    def __init__(
        self,
        settings: Settings,
        deduplicator: Deduplicator,
        brain: Brain,
        vector_store: VectorStore,
        style_profiles: StyleProfileCache | None = None,
    ) -> None:
        self._settings = settings
        self._deduplicator = deduplicator
        self._brain = brain
        self._vector_store = vector_store
        self._style_profiles = style_profiles
        self._queue: asyncio.Queue[dict] = asyncio.Queue(
            maxsize=settings.processor_queue_size
        )
        self._workers: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._workers:
            return
        for _ in range(self._settings.processor_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def enqueue(self, payload: dict) -> None:
        await self._queue.put(payload)

    async def _worker(self) -> None:
        while True:
            payload = await self._queue.get()
            try:
                await self.handle_message(**payload)
            except Exception:
                logger.exception("Message processing failed")
            finally:
                self._queue.task_done()

    async def handle_message(
        self,
        channel_name: str,
        channel_id: int | None,
        message_id: int,
        text: str,
    ) -> None:
        text = text[: self._settings.max_chars]
        logger.info("New post detected from {}", channel_name)
        post, created = await self._store_raw_post(
            channel_name, channel_id, message_id, text
        )
        if not created and post.processed_at is not None:
            logger.info("Post already processed. Skipping.")
            return

        dedup = await self._deduplicator.check(text)
        if dedup.is_duplicate:
            logger.info("Skipping duplicate post")
            await self._update_post(
                post_id=post.id,
                is_duplicate=True,
                similarity=dedup.similarity,
                duplicate_of=dedup.matched_id,
                processed_at=datetime.now(timezone.utc),
            )
            return

        doc_id = f"{channel_id or channel_name}:{message_id}"
        created_at = datetime.now(timezone.utc).timestamp()
        metadata = {
            "channel": channel_name,
            "message_id": message_id,
            "created_at": created_at,
        }
        await self._vector_store.add(doc_id, dedup.embedding, text, metadata)

        style_profile = None
        if self._style_profiles:
            style_profile = self._style_profiles.get(channel_id, channel_name)
        rewritten = await self._brain.generate(text, style_profile)
        logger.info("Generated post:\n{}", rewritten)
        await self._write_output(channel_name, message_id, rewritten)
        await self._update_post(
            post_id=post.id,
            rewritten_text=rewritten,
            is_duplicate=False,
            similarity=dedup.similarity,
            duplicate_of=dedup.matched_id,
            processed_at=datetime.now(timezone.utc),
        )

    async def _store_raw_post(
        self,
        channel_name: str,
        channel_id: int | None,
        message_id: int,
        text: str,
    ) -> tuple[Post, bool]:
        async with get_session() as session:
            channel = await self._get_or_create_channel(
                session, channel_name, channel_id
            )
            channel_db_id = channel.id
            post = Post(
                channel_id=channel_db_id,
                telegram_msg_id=message_id,
                text=text,
            )
            session.add(post)
            try:
                await session.commit()
                await session.refresh(post)
                return post, True
            except IntegrityError:
                await session.rollback()
                stmt = select(Post).where(
                    Post.channel_id == channel_db_id,
                    Post.telegram_msg_id == message_id,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one()
                logger.debug("Post already stored in database")
                return existing, False

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

    async def _update_post(self, post_id: int, **fields) -> None:
        async with get_session() as session:
            stmt = select(Post).where(Post.id == post_id)
            result = await session.execute(stmt)
            post = result.scalar_one_or_none()
            if not post:
                logger.warning("Post {} not found for update", post_id)
                return
            for key, value in fields.items():
                setattr(post, key, value)
            await session.commit()

    async def _write_output(self, channel_name: str, message_id: int, text: str) -> None:
        output_path = Path(self._settings.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        header = f"[{timestamp}] {channel_name} ({message_id})"
        payload = f"{header}\n{text}\n---\n"

        def _append():
            with output_path.open("a", encoding="utf-8") as handle:
                handle.write(payload)

        await asyncio.to_thread(_append)
