from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telethon import TelegramClient

from .config import get_settings
from .database import Channel, Post, get_session, init_db, init_engine
from .llm_client import LLMClient
from .vector_store import VectorStore


def _is_ad(text: str, stop_words: list[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in stop_words)


async def _get_or_create_channel(
    channel_name: str, channel_id: int | None
) -> Channel:
    async with get_session() as session:
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
        await session.commit()
        return channel


async def _store_post(channel_db_id: int, message_id: int, text: str) -> None:
    async with get_session() as session:
        post = Post(
            channel_id=channel_db_id,
            telegram_msg_id=message_id,
            text=text,
        )
        session.add(post)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.debug("Post already stored in database")


async def _backfill_channel(
    client: TelegramClient,
    llm_client: LLMClient,
    vector_store: VectorStore,
    channel_ref: str,
    limit: int,
    stop_words: list[str],
    max_chars: int,
    store_embeddings: bool,
) -> None:
    entity = await client.get_entity(channel_ref)
    channel_id = getattr(entity, "id", None)
    channel_name = getattr(entity, "username", None) or getattr(entity, "title", None)
    channel_name = channel_name or str(channel_id or channel_ref)

    channel = await _get_or_create_channel(channel_name, channel_id)
    logger.info("Backfilling channel {} (limit={})", channel_name, limit)

    async for message in client.iter_messages(entity, limit=limit):
        text = message.message or ""
        if not text.strip():
            continue
        if _is_ad(text, stop_words):
            continue

        trimmed = text[:max_chars]
        await _store_post(channel.id, message.id, trimmed)

        if not store_embeddings:
            continue

        embedding = await llm_client.embed(trimmed)
        doc_id = f"{channel_id or channel_name}:{message.id}"
        created_at = message.date or datetime.now(tz=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_ts = created_at.astimezone(timezone.utc).timestamp()
        metadata = {
            "channel": channel_name,
            "channel_id": channel_id,
            "message_id": message.id,
            "created_at": created_ts,
        }
        await vector_store.upsert(doc_id, embedding, trimmed, metadata)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill recent posts from Telegram channels."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of recent posts to fetch per channel.",
    )
    parser.add_argument(
        "--channels",
        type=str,
        default="",
        help="Comma-separated channel usernames to override TARGET_CHANNELS.",
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Store posts in SQLite only (skip vector embeddings).",
    )
    args = parser.parse_args()

    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    init_engine(settings)
    await init_db()

    channels = [
        part.strip()
        for part in (args.channels or "").split(",")
        if part.strip()
    ] or settings.target_channels
    if not channels:
        logger.error("No channels provided. Set TARGET_CHANNELS or use --channels.")
        return

    client = TelegramClient(
        settings.telethon_session,
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )
    await client.start()

    llm_client = LLMClient(settings)
    if not args.no_embeddings:
        await llm_client.health_check()
    vector_store = VectorStore(settings)

    for channel in channels:
        await _backfill_channel(
            client=client,
            llm_client=llm_client,
            vector_store=vector_store,
            channel_ref=channel,
            limit=args.limit,
            stop_words=settings.ad_stop_words,
            max_chars=settings.max_chars,
            store_embeddings=not args.no_embeddings,
        )

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
