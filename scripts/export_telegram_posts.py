from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from telethon import TelegramClient

from cannibal_core.config import get_settings


def _normalize_channel_ref(value: str) -> str:
    raw = value.strip()
    if not raw:
        return raw
    raw = re.sub(r"^https?://t\.me/", "", raw)
    raw = raw.lstrip("@")
    raw = raw.split("?")[0]
    raw = raw.split("/")[0]
    return raw


def _is_ad(text: str, stop_words: list[str]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in stop_words)


def _iso_utc(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def _export_channel(
    client: TelegramClient,
    channel_ref: str,
    limit: int,
    out_path: Path,
    skip_forwards: bool,
    skip_ads: bool,
    stop_words: list[str],
) -> int:
    entity = await client.get_entity(channel_ref)
    channel_id = getattr(entity, "id", None)
    channel_username = getattr(entity, "username", None)
    channel_title = getattr(entity, "title", None)
    channel_label = channel_username or channel_title or str(channel_id or channel_ref)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    exported = 0

    logger.info(
        "Exporting {} posts from {} into {}",
        limit,
        channel_label,
        out_path,
    )

    with out_path.open("w", encoding="utf-8") as handle:
        async for message in client.iter_messages(entity, limit=limit):
            if skip_forwards and message.fwd_from:
                continue

            text = message.message or ""
            if not text.strip():
                continue
            if skip_ads and _is_ad(text, stop_words):
                continue

            created_at = _iso_utc(message.date)
            link = None
            if channel_username:
                link = f"https://t.me/{channel_username}/{message.id}"

            payload = {
                "id": f"tg_{channel_label}_{message.id}",
                "channel": channel_label,
                "channel_id": channel_id,
                "message_id": message.id,
                "date": created_at,
                "source": "telegram",
                "link": link,
                "text": text,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            exported += 1

    return exported


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Telegram channel posts into JSONL."
    )
    parser.add_argument(
        "--channel",
        required=True,
        help="Channel username or link (e.g., @channel or https://t.me/channel).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of recent posts to fetch.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Output JSONL path. Defaults to data/style_corpus/<channel>/posts.jsonl",
    )
    parser.add_argument(
        "--include-forwards",
        action="store_true",
        help="Include forwarded posts (default: skipped).",
    )
    parser.add_argument(
        "--include-ads",
        action="store_true",
        help="Include posts containing ad stop-words (default: skipped).",
    )
    args = parser.parse_args()

    settings = get_settings()
    channel_ref = _normalize_channel_ref(args.channel)
    if not channel_ref:
        raise SystemExit("Channel reference is empty. Provide a valid channel.")

    out_path = Path(args.out) if args.out else Path(
        "data/style_corpus",
        channel_ref,
        "posts.jsonl",
    )

    client = TelegramClient(
        settings.telethon_session,
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )
    await client.start()

    exported = await _export_channel(
        client=client,
        channel_ref=channel_ref,
        limit=args.limit,
        out_path=out_path,
        skip_forwards=not args.include_forwards,
        skip_ads=not args.include_ads,
        stop_words=settings.ad_stop_words,
    )

    await client.disconnect()
    logger.info("Done. Exported {} posts.", exported)


if __name__ == "__main__":
    asyncio.run(main())
