from __future__ import annotations

import re
from collections import Counter
from statistics import mean
from typing import Any

from loguru import logger
from sqlalchemy import select

from .database import Channel, Post, get_session

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F6FF\U0001F700-\U0001FAFF\U00002700-\U000027BF\U000024C2-\U0001F251]"
)


class StyleProfileCache:
    def __init__(
        self,
        by_channel_id: dict[int, str],
        by_channel_name: dict[str, str],
    ) -> None:
        self._by_channel_id = by_channel_id
        self._by_channel_name = by_channel_name

    def get(self, channel_id: int | None, channel_name: str | None) -> str | None:
        if channel_id is not None and channel_id in self._by_channel_id:
            return self._by_channel_id[channel_id]
        if channel_name and channel_name in self._by_channel_name:
            return self._by_channel_name[channel_name]
        return None


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", cleaned)
    return [part for part in parts if part]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9']+", text)


def _opening_key(text: str, num_words: int = 2) -> str | None:
    words = _words(text)
    if not words:
        return None
    if len(words) >= num_words:
        return " ".join(words[:num_words]).lower()
    return words[0].lower()


def _lead_label(text: str) -> str | None:
    first_line = text.strip().splitlines()[0].strip()
    colon_idx = first_line.find(":")
    if 0 < colon_idx <= 15:
        label = first_line[:colon_idx].strip()
        if label and len(label.split()) <= 3:
            return label
    return None


def _count_list_lines(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return sum(1 for line in lines if line.startswith(("-", "•", "—")))


def _contains_emoji(text: str) -> bool:
    return bool(_EMOJI_RE.search(text))


def build_style_profile(texts: list[str]) -> dict[str, Any]:
    texts = [text for text in texts if text and text.strip()]
    if not texts:
        return {}

    char_lengths = [len(text) for text in texts]
    sentence_word_lengths: list[int] = []
    for text in texts:
        for sentence in _split_sentences(text):
            words = _words(sentence)
            if words:
                sentence_word_lengths.append(len(words))

    avg_chars = mean(char_lengths)
    avg_sentence_words = mean(sentence_word_lengths) if sentence_word_lengths else 0.0
    if avg_sentence_words <= 10:
        tempo = "short"
    elif avg_sentence_words <= 17:
        tempo = "medium"
    else:
        tempo = "long"

    opening_counter: Counter[str] = Counter()
    label_counter: Counter[str] = Counter()
    emoji_counter: Counter[str] = Counter()

    colon_posts = 0
    dash_posts = 0
    newline_posts = 0
    list_posts = 0
    emoji_posts = 0

    for text in texts:
        opening = _opening_key(text, 2)
        if opening:
            opening_counter[opening] += 1
        label = _lead_label(text)
        if label:
            label_counter[label] += 1

        if ":" in text:
            colon_posts += 1
        if "—" in text or " - " in text:
            dash_posts += 1
        if "\n" in text:
            newline_posts += 1
        if _count_list_lines(text) > 0:
            list_posts += 1

        if _contains_emoji(text):
            emoji_posts += 1
            for emoji in _EMOJI_RE.findall(text):
                emoji_counter[emoji] += 1

    total = len(texts)
    profile = {
        "sample_size": total,
        "avg_chars": round(avg_chars),
        "avg_sentence_words": round(avg_sentence_words, 1) if avg_sentence_words else None,
        "tempo": tempo,
        "top_openings": [item for item, _ in opening_counter.most_common(5)],
        "top_labels": [item for item, _ in label_counter.most_common(5)],
        "colon_ratio": colon_posts / total,
        "dash_ratio": dash_posts / total,
        "newline_ratio": newline_posts / total,
        "list_ratio": list_posts / total,
        "emoji_ratio": emoji_posts / total,
        "top_emojis": [item for item, _ in emoji_counter.most_common(5)],
    }
    return profile


def format_style_profile(profile: dict[str, Any]) -> str:
    if not profile:
        return ""
    parts: list[str] = []
    parts.append(f"Sample size: {profile['sample_size']} posts")
    parts.append(f"Avg length: ~{profile['avg_chars']} chars")
    if profile.get("avg_sentence_words"):
        parts.append(f"Avg sentence length: ~{profile['avg_sentence_words']} words")
    parts.append(f"Tempo: {profile['tempo']} sentences")

    if profile.get("top_labels"):
        parts.append(f"Lead labels: {', '.join(profile['top_labels'])}")
    if profile.get("top_openings"):
        parts.append(f"Common openings: {', '.join(profile['top_openings'])}")

    parts.append(
        "Formatting: "
        f"colon in {int(profile['colon_ratio'] * 100)}%, "
        f"dash in {int(profile['dash_ratio'] * 100)}%, "
        f"lists in {int(profile['list_ratio'] * 100)}%, "
        f"newlines in {int(profile['newline_ratio'] * 100)}%."
    )

    if profile.get("emoji_ratio", 0) > 0:
        emoji_part = f"Emojis in {int(profile['emoji_ratio'] * 100)}% posts"
        if profile.get("top_emojis"):
            emoji_part += f"; common: {', '.join(profile['top_emojis'])}"
        parts.append(emoji_part)

    return "\n".join(parts)


async def build_style_profiles(
    limit: int,
    channel_names: list[str] | None = None,
) -> StyleProfileCache:
    async with get_session() as session:
        stmt = select(Channel)
        if channel_names:
            stmt = stmt.where(Channel.name.in_(channel_names))
        result = await session.execute(stmt)
        channels = result.scalars().all()

        by_channel_id: dict[int, str] = {}
        by_channel_name: dict[str, str] = {}
        min_samples = max(10, limit // 3)

        for channel in channels:
            posts_stmt = (
                select(Post.text)
                .where(Post.channel_id == channel.id)
                .order_by(Post.created_at.desc())
                .limit(limit)
            )
            posts_result = await session.execute(posts_stmt)
            texts = [row[0] for row in posts_result.all()]
            if len(texts) < min_samples:
                logger.debug(
                    "Not enough posts for style profile: {} (have {}, need {}).",
                    channel.name,
                    len(texts),
                    min_samples,
                )
                continue

            profile = build_style_profile(texts)
            formatted = format_style_profile(profile)
            if not formatted:
                continue
            if channel.telegram_id is not None:
                by_channel_id[channel.telegram_id] = formatted
            by_channel_name[channel.name] = formatted

        return StyleProfileCache(by_channel_id, by_channel_name)
