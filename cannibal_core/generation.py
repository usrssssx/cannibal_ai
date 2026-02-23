from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UsernameNotOccupiedError
import asyncio

from .brain import Brain
from .config import Settings
from .database import Channel, Post, get_session
from .image_client import ImageClient
from .style_profile import build_style_examples, build_style_profiles


@dataclass(slots=True)
class GeneratedPost:
    source_channel: str
    message_id: int
    created_at: datetime
    rewritten_text: str
    image_url: str | None
    image_file: str | None


class GenerationError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def normalize_channel_ref(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw
    raw = raw.replace("https://t.me/", "").replace("http://t.me/", "")
    raw = raw.lstrip("@")
    raw = raw.split("?")[0]
    raw = raw.split("/")[0]
    return raw


def _is_ad(text: str, stop_words: Iterable[str]) -> bool:
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


async def ensure_style_corpus(
    settings: Settings,
    client: TelegramClient,
    channel_ref: str,
    limit: int,
    stop_words: list[str],
    max_chars: int,
) -> str:
    entity = await client.get_entity(channel_ref)
    channel_id = getattr(entity, "id", None)
    channel_name = getattr(entity, "username", None) or getattr(entity, "title", None)
    channel_name = channel_name or str(channel_id or channel_ref)

    channel = await _get_or_create_channel(channel_name, channel_id)

    attempts = 0
    while True:
        try:
            async for message in client.iter_messages(entity, limit=limit):
                text = message.message or ""
                if not text.strip():
                    continue
                if _is_ad(text, stop_words):
                    continue
                trimmed = text[:max_chars]
                await _store_post(channel.id, message.id, trimmed)
            break
        except FloodWaitError as exc:
            attempts += 1
            if attempts > settings.telegram_retry_attempts:
                raise
            sleep_for = min(exc.seconds, settings.telegram_flood_sleep_max)
            logger.warning("Telegram flood wait: sleeping {}s", sleep_for)
            await asyncio.sleep(sleep_for + settings.telegram_retry_base_delay)
        except Exception:
            attempts += 1
            if attempts > settings.telegram_retry_attempts:
                raise
            await asyncio.sleep(settings.telegram_retry_base_delay * attempts)

    return channel_name


async def fetch_source_posts(
    settings: Settings,
    client: TelegramClient,
    channel_ref: str,
    limit: int,
    stop_words: list[str],
    max_chars: int,
) -> list[tuple[str, int, str, datetime]]:
    entity = await client.get_entity(channel_ref)
    channel_name = getattr(entity, "username", None) or getattr(entity, "title", None)
    channel_name = channel_name or str(getattr(entity, "id", None) or channel_ref)
    results: list[tuple[str, int, str, datetime]] = []

    attempts = 0
    while True:
        try:
            async for message in client.iter_messages(entity, limit=limit):
                text = message.message or ""
                if not text.strip():
                    continue
                if _is_ad(text, stop_words):
                    continue
                trimmed = text[:max_chars]
                created_at = message.date or datetime.now(tz=timezone.utc)
                results.append((channel_name, message.id, trimmed, created_at))
            break
        except FloodWaitError as exc:
            attempts += 1
            if attempts > settings.telegram_retry_attempts:
                raise
            sleep_for = min(exc.seconds, settings.telegram_flood_sleep_max)
            logger.warning("Telegram flood wait: sleeping {}s", sleep_for)
            await asyncio.sleep(sleep_for + settings.telegram_retry_base_delay)
        except Exception:
            attempts += 1
            if attempts > settings.telegram_retry_attempts:
                raise
            await asyncio.sleep(settings.telegram_retry_base_delay * attempts)

    return results


async def generate_posts(
    settings: Settings,
    user_client: TelegramClient,
    brain: Brain,
    image_client: ImageClient | None,
    style_channel: str,
    source_channels: list[str],
    limit: int,
) -> tuple[list[GeneratedPost], list[str]]:
    if not style_channel:
        raise GenerationError("Канал стиля не задан.")
    if not source_channels:
        raise GenerationError("Источники не заданы.")

    try:
        style_channel_name = await ensure_style_corpus(
            settings=settings,
            client=user_client,
            channel_ref=style_channel,
            limit=settings.bot_style_limit,
            stop_words=settings.ad_stop_words,
            max_chars=settings.max_chars,
        )
    except UsernameNotOccupiedError as exc:
        raise GenerationError("Канал стиля не найден. Проверь username.") from exc
    except Exception as exc:
        logger.exception("Style corpus update failed")
        raise GenerationError("Не удалось получить стиль. Проверь доступ к каналу.") from exc

    style_profiles = await build_style_profiles(
        limit=settings.style_profile_posts,
        channel_names=[style_channel_name],
    )
    style_examples = await build_style_examples(
        limit=settings.style_profile_example_limit,
        max_examples=settings.style_profile_examples,
        min_chars=settings.style_profile_example_min_chars,
        max_chars=settings.style_profile_example_max_chars,
        channel_names=[style_channel_name],
    )
    style_profile = style_profiles.get(None, style_channel_name)
    examples = style_examples.get(None, style_channel_name)

    if not style_profile:
        raise GenerationError("Недостаточно постов для профиля стиля.")

    results: list[GeneratedPost] = []
    errors: list[str] = []

    for source in source_channels:
        try:
            posts = await fetch_source_posts(
                settings=settings,
                client=user_client,
                channel_ref=source,
                limit=limit,
                stop_words=settings.ad_stop_words,
                max_chars=settings.max_chars,
            )
        except UsernameNotOccupiedError:
            errors.append(f"Источник не найден: {source}")
            continue
        except Exception:
            logger.exception("Source fetch failed for {}", source)
            errors.append(f"Не удалось получить канал: {source}")
            continue

        if not posts:
            errors.append(f"Нет подходящих постов в {source}.")
            continue

        for channel_name, message_id, text, created_at in posts:
            rewritten = await brain.generate(
                text,
                style_profile=style_profile,
                style_examples=examples,
            )
            image_result = None
            if image_client:
                try:
                    image_result = await image_client.get_image(
                        text=text,
                        channel_name=channel_name,
                        message_id=message_id,
                    )
                except Exception:
                    logger.exception("Image generation failed")

            results.append(
                GeneratedPost(
                    source_channel=channel_name,
                    message_id=message_id,
                    created_at=created_at.astimezone(timezone.utc),
                    rewritten_text=rewritten,
                    image_url=image_result.url if image_result else None,
                    image_file=image_result.local_path if image_result else None,
                )
            )

    return results, errors
