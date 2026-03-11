from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from loguru import logger
from sqlalchemy import delete, select
from telethon import TelegramClient

from .brain import Brain
from .config import Settings
from .database import (
    EditorialGenerationOutput,
    EditorialGenerationRun,
    EditorialSource,
    EditorialSourcePost,
    EditorialTopic,
    EditorialTopicPost,
    EditorialTopicReport,
    WebAppSettings,
    get_session,
)
from .generation import normalize_channel_ref, prepare_style_bundle
from .image_client import ImageClient
from .llm_client import LLMClient


@dataclass(slots=True)
class SourcePostView:
    id: int
    source_ref: str
    source_title: str | None
    published_at: datetime
    text: str


@dataclass(slots=True)
class TopicDefinition:
    slug: str
    label: str
    summary: str


@dataclass(slots=True)
class GeneratedDraft:
    text: str
    source_post_ids: list[int]
    image_url: str | None
    image_file: str | None


def _slugify(value: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", value.lower()).strip("-")
    return raw or "topic"


T = TypeVar("T")


def _chunked(items: list[T], size: int) -> list[list[T]]:
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _parse_json_payload(text: str) -> Any:
    cleaned = text.strip()
    for candidate in (cleaned,):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.S)
    if match:
        return json.loads(match.group(1))
    raise ValueError("Model did not return valid JSON")


def _post_excerpt(text: str, max_chars: int = 500) -> str:
    return text.strip().replace("\n", " ")[:max_chars]


def _serialize_posts(posts: list[SourcePostView], max_chars: int = 500) -> str:
    lines = []
    for post in posts:
        lines.append(
            f"- id={post.id} | source={post.source_ref} | published_at={post.published_at.isoformat()} | "
            f"text={_post_excerpt(post.text, max_chars=max_chars)}"
        )
    return "\n".join(lines)


class TopicPlannerAgent:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def plan(
        self,
        posts: list[SourcePostView],
        max_categories: int,
    ) -> list[TopicDefinition]:
        if not posts:
            return []
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты аналитик редакции. По набору постов выдели главные темы за период. "
                    "Верни только JSON вида "
                    '{"categories":[{"label":"...", "slug":"...", "summary":"..."}]}. '
                    "Категории должны быть широкими, не дублироваться, и быть полезными "
                    "для отбора контента редактором. Пиши label и summary по-русски."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Нужно предложить не более {max_categories} категорий.\n\n"
                    "Посты:\n"
                    f"{_serialize_posts(posts[: max_categories * 8])}"
                ),
            },
        ]
        raw = await self._llm_client.chat(messages, temperature=0.2, max_tokens=1200)
        try:
            payload = _parse_json_payload(raw)
        except Exception:
            logger.exception("Topic planning JSON parsing failed")
            return [TopicDefinition(slug="other", label="Разное", summary="Прочие темы.")]

        categories = payload.get("categories") if isinstance(payload, dict) else None
        if not isinstance(categories, list):
            return [TopicDefinition(slug="other", label="Разное", summary="Прочие темы.")]

        seen: set[str] = set()
        results: list[TopicDefinition] = []
        for item in categories:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            summary = str(item.get("summary") or "").strip()
            slug = _slugify(str(item.get("slug") or label))
            if not label or not summary or slug in seen:
                continue
            seen.add(slug)
            results.append(TopicDefinition(slug=slug, label=label, summary=summary))
            if len(results) >= max_categories:
                break

        return results or [TopicDefinition(slug="other", label="Разное", summary="Прочие темы.")]


class TopicClassifierAgent:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def classify(
        self,
        posts: list[SourcePostView],
        topics: list[TopicDefinition],
        batch_size: int,
    ) -> dict[int, list[str]]:
        if not posts or not topics:
            return {}
        mapping: dict[int, list[str]] = {}
        topics_block = "\n".join(
            f"- slug={topic.slug} | label={topic.label} | summary={topic.summary}"
            for topic in topics
        )
        for batch in _chunked(posts, max(1, batch_size)):
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Ты роутер редакции. Для каждого поста назначь 1-3 категории из "
                        "предложенного списка. Верни только JSON вида "
                        '{"items":[{"post_id":1,"topic_slugs":["slug-a","slug-b"]}]} '
                        "и используй только известные topic_slugs."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Категории:\n"
                        f"{topics_block}\n\n"
                        "Посты:\n"
                        f"{_serialize_posts(batch)}"
                    ),
                },
            ]
            raw = await self._llm_client.chat(messages, temperature=0.1, max_tokens=1400)
            try:
                payload = _parse_json_payload(raw)
            except Exception:
                logger.exception("Topic classification JSON parsing failed")
                for post in batch:
                    mapping[post.id] = [topics[0].slug]
                continue

            items = payload.get("items") if isinstance(payload, dict) else None
            valid_slugs = {topic.slug for topic in topics}
            if not isinstance(items, list):
                for post in batch:
                    mapping[post.id] = [topics[0].slug]
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    post_id = int(item.get("post_id"))
                except (TypeError, ValueError):
                    continue
                slugs = [
                    slug
                    for slug in item.get("topic_slugs") or []
                    if isinstance(slug, str) and slug in valid_slugs
                ]
                if slugs:
                    mapping[post_id] = list(dict.fromkeys(slugs))[:3]

            for post in batch:
                mapping.setdefault(post.id, [topics[0].slug])
        return mapping


class EditorialPlannerAgent:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def build_brief(self, post: SourcePostView) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты редактор-аналитик. Вытащи из поста факты, ключевой тезис, цифры, "
                    "имена и контекст. Верни короткий редакторский brief в буллетах. "
                    "Не придумывай ничего сверх исходника."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Источник: {post.source_ref}\n"
                    f"Дата: {post.published_at.isoformat()}\n"
                    f"Пост:\n{post.text}"
                ),
            },
        ]
        return await self._llm_client.chat(messages, temperature=0.2, max_tokens=500)


class EditorialWriterAgent:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def write(
        self,
        brief: str,
        style_profile: str,
        style_examples: list[str],
    ) -> str:
        examples_block = "\n\n".join(
            f"Example {idx + 1}:\n{example}"
            for idx, example in enumerate(style_examples)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты редактор Telegram-канала. По редакторскому brief напиши готовый "
                    "пост в стиле референс-канала. Не добавляй фактов, которых нет в brief."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Style profile:\n"
                    f"{style_profile}\n\n"
                    "Style examples:\n"
                    f"{examples_block}\n\n"
                    "Brief:\n"
                    f"{brief}\n\n"
                    "Напиши итоговый пост на русском или языке brief, сохрани факты, "
                    "сделай текст публикабельным, без заголовка вне стилистики автора."
                ),
            },
        ]
        return await self._llm_client.chat(messages, temperature=0.4, max_tokens=700)


class NewsroomOrchestrator:
    def __init__(
        self,
        llm_client: LLMClient,
        brain: Brain,
        settings: Settings,
    ) -> None:
        self._llm_client = llm_client
        self._brain = brain
        self._settings = settings
        self._topic_planner = TopicPlannerAgent(llm_client)
        self._topic_classifier = TopicClassifierAgent(llm_client)
        self._editorial_planner = EditorialPlannerAgent(llm_client)
        self._editorial_writer = EditorialWriterAgent(llm_client)

    async def build_topics(
        self,
        posts: list[SourcePostView],
    ) -> tuple[list[TopicDefinition], dict[int, list[str]]]:
        topics = await self._topic_planner.plan(
            posts=posts,
            max_categories=self._settings.editorial_topic_max_categories,
        )
        mapping = await self._topic_classifier.classify(
            posts=posts,
            topics=topics,
            batch_size=self._settings.editorial_topic_batch_size,
        )
        return topics, mapping

    async def generate_drafts(
        self,
        posts: list[SourcePostView],
        style_channel: str,
        user_client: TelegramClient,
        image_client: ImageClient | None = None,
    ) -> list[GeneratedDraft]:
        style = await prepare_style_bundle(
            settings=self._settings,
            client=user_client,
            style_channel=style_channel,
        )
        drafts: list[GeneratedDraft] = []
        for post in posts:
            brief = await self._editorial_planner.build_brief(post)
            text = await self._editorial_writer.write(
                brief=brief,
                style_profile=style.profile,
                style_examples=style.examples,
            )
            image_url = None
            image_file = None
            if image_client:
                try:
                    image = await image_client.get_image(
                        text=post.text,
                        channel_name=post.source_ref,
                        message_id=post.id,
                    )
                    if image:
                        image_url = image.url
                        image_file = image.local_path
                except Exception:
                    logger.exception("Editorial image generation failed")
            drafts.append(
                GeneratedDraft(
                    text=text,
                    source_post_ids=[post.id],
                    image_url=image_url,
                    image_file=image_file,
                )
            )
        return drafts


async def upsert_editorial_sources(
    user_id: int,
    sources: list[dict[str, Any]],
    replace: bool = False,
) -> None:
    async with get_session() as session:
        active_refs = {str(item["channel_ref"]) for item in sources}
        stmt = select(EditorialSource).where(EditorialSource.user_id == user_id)
        result = await session.execute(stmt)
        existing = {item.channel_ref: item for item in result.scalars().all()}

        if replace:
            for item in existing.values():
                item.is_active = item.channel_ref in active_refs

        for item in sources:
            channel_ref = str(item["channel_ref"])
            existing_source = existing.get(channel_ref)
            if existing_source:
                existing_source.channel_title = item.get("channel_title")
                existing_source.telegram_id = item.get("telegram_id")
                existing_source.added_via = str(item.get("added_via") or "manual")
                existing_source.is_active = True
                continue
            session.add(
                EditorialSource(
                    user_id=user_id,
                    channel_ref=channel_ref,
                    channel_title=item.get("channel_title"),
                    telegram_id=item.get("telegram_id"),
                    added_via=str(item.get("added_via") or "manual"),
                    is_active=True,
                )
            )
        await session.commit()


async def list_editorial_sources(user_id: int) -> list[dict[str, Any]]:
    async with get_session() as session:
        stmt = (
            select(EditorialSource)
            .where(EditorialSource.user_id == user_id)
            .where(EditorialSource.is_active.is_(True))
            .order_by(EditorialSource.channel_ref.asc())
        )
        result = await session.execute(stmt)
        items = result.scalars().all()
    return [
        {
            "id": item.id,
            "channel_ref": item.channel_ref,
            "channel_title": item.channel_title,
            "telegram_id": item.telegram_id,
            "added_via": item.added_via,
        }
        for item in items
    ]


async def resolve_editorial_source(
    client: TelegramClient,
    raw_ref: str | int,
) -> dict[str, Any]:
    entity_ref: str | int
    if isinstance(raw_ref, int):
        entity_ref = raw_ref
    else:
        normalized = normalize_channel_ref(raw_ref)
        if not normalized:
            raise ValueError("Channel ref is empty")
        entity_ref = normalized
    entity = await client.get_entity(entity_ref)
    channel_ref = (
        normalize_channel_ref(str(getattr(entity, "username", None) or ""))
        or str(getattr(entity, "id", None) or entity_ref)
    )
    channel_title = getattr(entity, "title", None) or getattr(entity, "username", None)
    telegram_id = getattr(entity, "id", None)
    return {
        "channel_ref": channel_ref,
        "channel_title": channel_title,
        "telegram_id": telegram_id,
        "added_via": "manual",
    }


async def refresh_editorial_posts(
    settings: Settings,
    user_client: TelegramClient,
    user_id: int,
    days: int,
) -> tuple[list[SourcePostView], list[str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with get_session() as session:
        stmt = (
            select(EditorialSource)
            .where(EditorialSource.user_id == user_id)
            .where(EditorialSource.is_active.is_(True))
        )
        result = await session.execute(stmt)
        sources = result.scalars().all()

    errors: list[str] = []
    for source in sources:
        try:
            entity = await user_client.get_entity(source.telegram_id or source.channel_ref)
        except Exception:
            logger.exception("Failed to resolve editorial source {}", source.channel_ref)
            errors.append(f"Не удалось получить источник: {source.channel_ref}")
            continue

        channel_title = getattr(entity, "title", None) or source.channel_title
        channel_ref = (
            normalize_channel_ref(getattr(entity, "username", None) or source.channel_ref)
            or source.channel_ref
        )
        telegram_id = getattr(entity, "id", None) or source.telegram_id

        async with get_session() as session:
            db_source = await session.get(EditorialSource, source.id)
            if db_source:
                db_source.channel_title = channel_title
                db_source.channel_ref = channel_ref
                db_source.telegram_id = telegram_id
                await session.commit()

        try:
            async for message in user_client.iter_messages(
                entity, limit=settings.editorial_source_sync_limit
            ):
                text = (message.message or "").strip()
                if not text:
                    continue
                if any(stop_word in text.lower() for stop_word in settings.ad_stop_words):
                    continue
                published_at = message.date or datetime.now(timezone.utc)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                if published_at < cutoff:
                    break
                async with get_session() as session:
                    stmt = select(EditorialSourcePost).where(
                        EditorialSourcePost.source_id == source.id,
                        EditorialSourcePost.telegram_msg_id == message.id,
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.text = text[: settings.max_chars]
                        existing.published_at = published_at
                    else:
                        session.add(
                            EditorialSourcePost(
                                source_id=source.id,
                                telegram_msg_id=message.id,
                                text=text[: settings.max_chars],
                                published_at=published_at,
                            )
                        )
                    await session.commit()
        except Exception:
            logger.exception("Failed to sync editorial posts for {}", source.channel_ref)
            errors.append(f"Не удалось обновить посты источника: {source.channel_ref}")

    async with get_session() as session:
        stmt = (
            select(EditorialSourcePost, EditorialSource)
            .join(EditorialSource, EditorialSource.id == EditorialSourcePost.source_id)
            .where(EditorialSource.user_id == user_id)
            .where(EditorialSource.is_active.is_(True))
            .where(EditorialSourcePost.published_at >= cutoff)
            .order_by(EditorialSourcePost.published_at.desc())
            .limit(settings.editorial_topic_max_posts)
        )
        result = await session.execute(stmt)
        rows = result.all()

    posts = [
        SourcePostView(
            id=post.id,
            source_ref=source.channel_ref,
            source_title=source.channel_title,
            published_at=post.published_at,
            text=post.text,
        )
        for post, source in rows
    ]
    return posts, errors


async def create_topic_report(
    user_id: int,
    style_channel: str | None,
    sources: list[str],
    window_days: int,
) -> int:
    async with get_session() as session:
        report = EditorialTopicReport(
            user_id=user_id,
            style_channel=style_channel,
            sources_csv=",".join(sources),
            window_days=window_days,
            status="started",
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report.id


async def finish_topic_report(
    report_id: int,
    topics: list[TopicDefinition],
    mapping: dict[int, list[str]],
    posts: list[SourcePostView],
    errors: list[str],
) -> None:
    async with get_session() as session:
        report = await session.get(EditorialTopicReport, report_id)
        if not report:
            return
        report.status = "done" if not errors else "partial"
        report.error = "; ".join(errors) if errors else None
        report.posts_count = len(posts)
        report.categories_count = len(topics)

        await session.execute(
            delete(EditorialTopicPost).where(
                EditorialTopicPost.topic_id.in_(
                    select(EditorialTopic.id).where(EditorialTopic.report_id == report_id)
                )
            )
        )
        await session.execute(
            delete(EditorialTopic).where(EditorialTopic.report_id == report_id)
        )

        topic_by_slug: dict[str, EditorialTopic] = {}
        for topic in topics:
            obj = EditorialTopic(
                report_id=report_id,
                slug=topic.slug,
                label=topic.label,
                summary=topic.summary,
                post_count=0,
            )
            session.add(obj)
            await session.flush()
            topic_by_slug[topic.slug] = obj

        counts: dict[str, int] = {}
        for post in posts:
            for slug in mapping.get(post.id, []):
                topic = topic_by_slug.get(slug)
                if not topic:
                    continue
                counts[slug] = counts.get(slug, 0) + 1
                session.add(EditorialTopicPost(topic_id=topic.id, post_id=post.id))

        for slug, count in counts.items():
            topic_by_slug[slug].post_count = count

        await session.commit()


async def fail_topic_report(report_id: int, message: str) -> None:
    async with get_session() as session:
        report = await session.get(EditorialTopicReport, report_id)
        if not report:
            return
        report.status = "error"
        report.error = message
        await session.commit()


async def get_latest_topic_report(user_id: int) -> dict[str, Any]:
    async with get_session() as session:
        stmt = (
            select(EditorialTopicReport)
            .where(EditorialTopicReport.user_id == user_id)
            .order_by(EditorialTopicReport.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()
        if not report:
            return {}
        topics_stmt = (
            select(EditorialTopic)
            .where(EditorialTopic.report_id == report.id)
            .order_by(EditorialTopic.post_count.desc(), EditorialTopic.label.asc())
        )
        topics_result = await session.execute(topics_stmt)
        topics = topics_result.scalars().all()
    return {
        "id": report.id,
        "status": report.status,
        "error": report.error,
        "style_channel": report.style_channel,
        "sources": [part for part in report.sources_csv.split(",") if part.strip()],
        "window_days": report.window_days,
        "posts_count": report.posts_count,
        "categories_count": report.categories_count,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "topics": [
            {
                "id": topic.id,
                "slug": topic.slug,
                "label": topic.label,
                "summary": topic.summary,
                "post_count": topic.post_count,
            }
            for topic in topics
        ],
    }


async def get_topic_posts(user_id: int, topic_id: int) -> list[dict[str, Any]]:
    async with get_session() as session:
        stmt = (
            select(EditorialSourcePost, EditorialSource, EditorialTopic)
            .join(EditorialTopicPost, EditorialTopicPost.post_id == EditorialSourcePost.id)
            .join(EditorialTopic, EditorialTopic.id == EditorialTopicPost.topic_id)
            .join(EditorialTopicReport, EditorialTopicReport.id == EditorialTopic.report_id)
            .join(EditorialSource, EditorialSource.id == EditorialSourcePost.source_id)
            .where(EditorialTopic.id == topic_id)
            .where(EditorialTopicReport.user_id == user_id)
            .order_by(EditorialSourcePost.published_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()
    return [
        {
            "id": post.id,
            "source_ref": source.channel_ref,
            "source_title": source.channel_title,
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "text": post.text,
            "telegram_message_id": post.telegram_msg_id,
        }
        for post, source, _topic in rows
    ]


async def create_generation_run(
    user_id: int,
    style_channel: str,
    selected_post_ids: list[int],
) -> int:
    async with get_session() as session:
        run = EditorialGenerationRun(
            user_id=user_id,
            style_channel=style_channel,
            selected_post_ids_csv=",".join(str(item) for item in selected_post_ids),
            status="started",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


async def finish_generation_run(
    run_id: int,
    drafts: list[GeneratedDraft],
    errors: list[str] | None = None,
) -> None:
    async with get_session() as session:
        run = await session.get(EditorialGenerationRun, run_id)
        if not run:
            return
        run.status = "done" if not errors else "partial"
        run.error = "; ".join(errors) if errors else None
        run.outputs_count = len(drafts)
        for draft in drafts:
            session.add(
                EditorialGenerationOutput(
                    run_id=run_id,
                    source_post_ids_csv=",".join(str(item) for item in draft.source_post_ids),
                    text=draft.text,
                    image_url=draft.image_url,
                    image_file=draft.image_file,
                )
            )
        await session.commit()


async def fail_generation_run(run_id: int, message: str) -> None:
    async with get_session() as session:
        run = await session.get(EditorialGenerationRun, run_id)
        if not run:
            return
        run.status = "error"
        run.error = message
        await session.commit()


async def get_source_posts_by_ids(user_id: int, post_ids: list[int]) -> list[SourcePostView]:
    async with get_session() as session:
        stmt = (
            select(EditorialSourcePost, EditorialSource)
            .join(EditorialSource, EditorialSource.id == EditorialSourcePost.source_id)
            .where(EditorialSource.user_id == user_id)
            .where(EditorialSourcePost.id.in_(post_ids))
            .order_by(EditorialSourcePost.published_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()
    return [
        SourcePostView(
            id=post.id,
            source_ref=source.channel_ref,
            source_title=source.channel_title,
            published_at=post.published_at,
            text=post.text,
        )
        for post, source in rows
    ]


async def sync_editorial_settings(
    user_id: int,
    style_channel: str,
    sources: list[str],
) -> None:
    async with get_session() as session:
        obj = await session.get(WebAppSettings, user_id)
        sources_csv = ",".join(sources)
        if obj:
            obj.style_channel = style_channel
            obj.sources_csv = sources_csv
        else:
            session.add(
                WebAppSettings(
                    user_id=user_id,
                    style_channel=style_channel,
                    sources_csv=sources_csv,
                    limit=1,
                    with_images=False,
                )
            )
        await session.commit()
