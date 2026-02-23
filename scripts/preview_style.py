from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from cannibal_core.brain import Brain
from cannibal_core.config import get_settings
from cannibal_core.database import Channel, get_session, init_db, init_engine
from cannibal_core.llm_client import LLMClient
from cannibal_core.logging_setup import configure_logging
from cannibal_core.style_profile import build_style_examples, build_style_profiles


async def _list_channels() -> list[str]:
    async with get_session() as session:
        result = await session.execute(select(Channel).order_by(Channel.id))
        channels = result.scalars().all()
        return [channel.name for channel in channels if channel.name]


def _read_text(text: str | None, text_file: str | None) -> str:
    if text and text.strip():
        return text.strip()
    if text_file:
        content = Path(text_file).read_text(encoding="utf-8")
        return content.strip()
    raise SystemExit("Provide --text or --text-file.")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview rewrite with a style profile from stored posts."
    )
    parser.add_argument(
        "--channel",
        type=str,
        default="",
        help="Channel name from DB. If omitted, the first stored channel is used.",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="",
        help="Source text to rewrite.",
    )
    parser.add_argument(
        "--text-file",
        type=str,
        default="",
        help="Path to a file with source text to rewrite.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=80,
        help="How many recent posts to use for style profile.",
    )
    parser.add_argument(
        "--show-profile",
        action="store_true",
        help="Print the computed style profile.",
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        help="List channels found in DB and exit.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    await init_db()

    if args.list_channels:
        channels = await _list_channels()
        if not channels:
            raise SystemExit("No channels found in DB. Run backfill first.")
        for name in channels:
            print(name)
        return

    channel_name = args.channel.strip()
    if not channel_name:
        channels = await _list_channels()
        if not channels:
            raise SystemExit("No channels found in DB. Run backfill first.")
        channel_name = channels[0]

    source_text = _read_text(args.text, args.text_file)
    if len(source_text) > settings.max_chars:
        source_text = source_text[: settings.max_chars]

    llm_client = LLMClient(settings)
    await llm_client.health_check()
    brain = Brain(llm_client, settings)

    style_profiles = await build_style_profiles(
        limit=args.limit,
        channel_names=[channel_name],
    )
    style_examples = await build_style_examples(
        limit=max(args.limit, settings.style_profile_example_limit),
        max_examples=settings.style_profile_examples,
        min_chars=settings.style_profile_example_min_chars,
        max_chars=settings.style_profile_example_max_chars,
        channel_names=[channel_name],
    )
    style_profile = style_profiles.get(None, channel_name)
    examples = style_examples.get(None, channel_name)
    if not style_profile:
        raise SystemExit(
            f"Style profile for '{channel_name}' not found or too few samples."
        )

    if args.show_profile:
        print("Style profile:")
        print(style_profile)
        print("----")

    rewritten = await brain.generate(
        source_text,
        style_profile=style_profile,
        style_examples=examples,
    )
    print(rewritten)


if __name__ == "__main__":
    asyncio.run(main())
