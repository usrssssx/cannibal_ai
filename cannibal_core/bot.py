from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass, field

from loguru import logger
from telethon import TelegramClient, events
from telethon import Button
from telethon.tl import types
from .alerts import send_alert_sync
from .brain import Brain
from .config import get_settings
from .database import init_db, init_engine
from .editorial import resolve_editorial_source, upsert_editorial_sources
from .generation import GenerationError, generate_posts, normalize_channel_ref
from .image_client import ImageClient
from .llm_client import LLMClient
from .logging_setup import configure_logging


@dataclass(slots=True)
class BotState:
    style_channel: str | None = None
    source_channels: list[str] = field(default_factory=list)
    limit: int | None = None
    awaiting: str | None = None
    last_posts: list[str] = field(default_factory=list)


def _format_channels(channels: list[str]) -> str:
    if not channels:
        return "—"
    return ", ".join(channels)


def _normalize_channel(value: str) -> str:
    return normalize_channel_ref(value)


def _parse_channel_list(raw: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[,\n]+", raw) if part.strip()]
    channels = [_normalize_channel(part) for part in parts]
    return [channel for channel in channels if channel]


def _is_allowed(settings, user_id: int | None) -> bool:
    if not settings.bot_allowed_users:
        return True
    if user_id is None:
        return False
    return user_id in settings.bot_allowed_users


def _help_text() -> str:
    return (
        "Используй кнопки внизу сообщения для управления.\n\n"
        "Команды (опционально):\n"
        "/style <channel> — канал для стиля\n"
        "/sources <ch1,ch2,...> — источники новостей\n"
        "/limit <N> — сколько последних постов брать с каждого источника\n"
        "/run — сгенерировать посты\n"
        "/status — показать текущие настройки\n"
        "/reset — очистить настройки\n"
        "/menu — панель управления"
    )


def _welcome_text(settings) -> str:
    guide = settings.bot_guide_url or "https://docs.google.com/document/d/1TV_qhhPvhgYUM-mPNypklG6pRC_mmX0Bzvo_l8DFCPQ/edit?usp=sharing"
    return (
        "🤖 Добро пожаловать в cannibal_ai\n\n"
        "Я — бот для автоматического мониторинга Telegram-каналов, удаления дублей "
        "и рерайта новостей с сохранением Tone of Voice.\n\n"
        "Помогаю превратить поток контента в аккуратные, уникальные и готовые к "
        "публикации посты.\n\n"
        "🚀 Что я умею:\n\n"
        "• 📡 Отслеживать новые публикации в выбранных каналах\n"
        "• 🚫 Фильтровать рекламу по стоп-словам\n"
        "• 🧠 Находить и удалять дубли через эмбеддинги\n"
        "• ✍️ Переписывать тексты в стиле вашего канала\n"
        "• 🖼 Подбирать или генерировать изображение\n"
        "• 💾 Сохранять исходные данные и формировать итоговый файл\n\n"
        "⚙️ Как начать:\n\n"
        "1️⃣ Настройте стиль\n"
        "2️⃣ Добавьте каналы для мониторинга\n"
        "3️⃣ Запустите обработку\n\n"
        "Готово — бот сделает остальное автоматически.\n\n"
        f'<a href="{guide}">📘 Подробная инструкция по работе с ботом Cannibal AI</a>'
    )


async def _run_generation(
    event,
    settings,
    user_client: TelegramClient,
    brain: Brain,
    image_client: ImageClient | None,
    state: BotState,
    limit: int,
) -> None:
    try:
        state.last_posts = []
        results, errors = await generate_posts(
            settings=settings,
            user_client=user_client,
            brain=brain,
            image_client=image_client,
            style_channel=state.style_channel or "",
            source_channels=state.source_channels,
            limit=limit,
        )
    except GenerationError as exc:
        await event.respond(exc.message)
        return

    for item in errors:
        await event.respond(f"⚠️ {item}")

    total = 0
    for post in results:
        header = "📝 Готовый пост"
        meta = (
            f"Источник: {post.source_channel}\n"
            f"Дата: {post.created_at.isoformat()}"
        )
        media = []
        if post.image_url:
            media.append(f"IMAGE_URL: {post.image_url}")
        if post.image_file:
            media.append(f"IMAGE_FILE: {post.image_file}")
        blocks = [header, meta]
        if media:
            blocks.append("\n".join(media))
        blocks.append(post.rewritten_text)
        state.last_posts.append(post.rewritten_text)
        await event.respond("\n\n".join(blocks), buttons=_result_buttons(settings, total))
        total += 1

    await event.respond(f"Готово. Отправлено постов: {total}")


def _menu_text(settings, state: BotState) -> str:
    style = state.style_channel or "—"
    sources = _format_channels(state.source_channels)
    limit = state.limit or settings.bot_source_limit
    return (
        "Панель управления\n"
        f"Стиль: {style}\n"
        f"Источники: {sources}\n"
        f"Лимит: {limit}\n\n"
        "Подсказка: указывай каналы без @, через запятую."
    )


def _menu_buttons(settings):
    rows = [
        [Button.inline("Стиль", b"style"), Button.inline("Источники", b"sources")],
        [Button.inline("Лимит", b"limit"), Button.inline("Запуск", b"run")],
        [Button.inline("Статус", b"status"), Button.inline("Сброс", b"reset")],
    ]
    if settings.webapp_url:
        rows.append([types.KeyboardButtonWebView("Открыть WebApp", settings.webapp_url)])
    rows.append([Button.inline("Помощь", b"help")])
    return rows


def _result_buttons(settings, idx: int):
    buttons = [
        [Button.inline("Скопировать текст", f"copy:{idx}".encode("utf-8"))],
        [Button.inline("Повторить запуск", b"repeat")],
    ]
    if settings.webapp_url:
        buttons.insert(
            1, [types.KeyboardButtonWebView("Открыть WebApp", settings.webapp_url)]
        )
    return buttons


async def _show_menu(event, settings, state: BotState, edit: bool = False) -> None:
    text = _menu_text(settings, state)
    buttons = _menu_buttons(settings)
    if edit and hasattr(event, "edit"):
        try:
            await event.edit(text, buttons=buttons)
            return
        except Exception:
            logger.exception("Failed to edit menu message")
    await event.respond(text, buttons=buttons)


async def _try_capture_forwarded_source(event, settings, user_client, state: BotState) -> bool:
    message = getattr(event, "message", None)
    forward = getattr(message, "forward", None)
    chat = getattr(forward, "chat", None) if forward else None
    if not chat:
        return False

    raw_ref = getattr(chat, "username", None) or getattr(chat, "id", None)
    if raw_ref is None:
        raw_ref = getattr(chat, "title", None)
    if raw_ref is None:
        return False

    try:
        source = await resolve_editorial_source(user_client, raw_ref)
        source["added_via"] = "forward"
        await upsert_editorial_sources(event.sender_id, [source], replace=False)
    except Exception:
        logger.exception("Failed to save forwarded source")
        await event.reply("Не удалось распознать пересланный канал как источник.")
        return True

    channel_ref = source["channel_ref"]
    if channel_ref not in state.source_channels:
        state.source_channels.append(channel_ref)
    state.awaiting = None
    await event.reply(f"Источник сохранён из пересланного поста: {channel_ref}")
    await _show_menu(event, settings, state, edit=False)
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bot runner.")
    parser.add_argument(
        "--with-images",
        action="store_true",
        help="Enable image generation for bot responses.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)

    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is required to run the bot.")
    if settings.enforce_allowed_users and not settings.bot_allowed_users:
        raise SystemExit("BOT_ALLOWED_USERS is required when ENFORCE_ALLOWED_USERS=true.")
    if not settings.bot_allowed_users:
        logger.warning("BOT_ALLOWED_USERS is empty. Bot доступен всем пользователям.")

    init_engine(settings)
    await init_db()

    user_client = TelegramClient(
        settings.bot_user_session or settings.telethon_session,
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )
    bot_client = TelegramClient(
        settings.bot_session,
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )

    await user_client.start()
    await bot_client.start(bot_token=settings.bot_token)

    llm_client = LLMClient(settings)
    await llm_client.health_check()
    brain = Brain(llm_client, settings)
    image_client = ImageClient(settings) if args.with_images and settings.image_enabled else None

    state_by_user: dict[int, BotState] = {}

    @bot_client.on(events.NewMessage(pattern=r"^/start$"))
    async def _start(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        await event.reply(
            _welcome_text(settings),
            parse_mode="html",
            link_preview=False,
        )
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/menu$"))
    async def _menu(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/help$"))
    async def _help(event):
        if not _is_allowed(settings, event.sender_id):
            return
        await event.reply(_help_text())

    @bot_client.on(events.NewMessage(pattern=r"^/reset$"))
    async def _reset(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state_by_user.pop(event.sender_id, None)
        state = state_by_user.setdefault(event.sender_id, BotState())
        await event.reply("Настройки сброшены.")
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/status$"))
    async def _status(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state = state_by_user.get(event.sender_id) or BotState()
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/style\\s+(.+)$"))
    async def _style(event):
        if not _is_allowed(settings, event.sender_id):
            return
        raw = event.pattern_match.group(1)
        channel = _normalize_channel(raw)
        if not channel:
            await event.reply("Укажи канал после /style.")
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        state.style_channel = channel
        state.awaiting = None
        await event.reply(f"Канал стиля установлен: {channel}")
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/sources\\s+(.+)$"))
    async def _sources(event):
        if not _is_allowed(settings, event.sender_id):
            return
        raw = event.pattern_match.group(1)
        channels = _parse_channel_list(raw)
        if not channels:
            await event.reply("Укажи каналы через запятую после /sources.")
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        state.source_channels = channels
        state.awaiting = None
        await event.reply(f"Источники обновлены: {', '.join(channels)}")
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/limit\\s+(\\d+)$"))
    async def _limit(event):
        if not _is_allowed(settings, event.sender_id):
            return
        value = int(event.pattern_match.group(1))
        if value <= 0 or value > 50:
            await event.reply("Лимит должен быть от 1 до 50.")
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        state.limit = value
        state.awaiting = None
        await event.reply(f"Лимит установлен: {value}")
        await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.NewMessage(pattern=r"^/run$"))
    async def _run(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state = state_by_user.get(event.sender_id) or BotState()
        if not state.style_channel:
            await event.reply("Сначала задай канал стиля.")
            return
        if not state.source_channels:
            await event.reply("Сначала задай источники.")
            return

        limit = state.limit or settings.bot_source_limit
        await event.reply("Запускаю. Это может занять 1–2 минуты.")

        await _run_generation(
            event=event,
            settings=settings,
            user_client=user_client,
            brain=brain,
            image_client=image_client,
            state=state,
            limit=limit,
        )

    @bot_client.on(events.NewMessage)
    async def _text_input(event):
        if not _is_allowed(settings, event.sender_id):
            return
        state = state_by_user.setdefault(event.sender_id, BotState())
        if await _try_capture_forwarded_source(event, settings, user_client, state):
            return
        if not event.raw_text or event.raw_text.startswith("/"):
            return
        if not state.awaiting:
            return

        raw = event.raw_text.strip()
        if state.awaiting == "style":
            channel = _normalize_channel(raw)
            if not channel:
                await event.reply("Укажи канал для стиля.")
                return
            state.style_channel = channel
            state.awaiting = None
            await event.reply(f"Канал стиля установлен: {channel}")
            await _show_menu(event, settings, state, edit=False)
            return

        if state.awaiting == "sources":
            channels = _parse_channel_list(raw)
            if not channels:
                await event.reply("Укажи источники через запятую.")
                return
            state.source_channels = channels
            state.awaiting = None
            await event.reply(f"Источники обновлены: {', '.join(channels)}")
            await _show_menu(event, settings, state, edit=False)
            return

        if state.awaiting == "limit":
            try:
                value = int(raw)
            except ValueError:
                await event.reply("Лимит должен быть числом.")
                return
            if value <= 0 or value > 50:
                await event.reply("Лимит должен быть от 1 до 50.")
                return
            state.limit = value
            state.awaiting = None
            await event.reply(f"Лимит установлен: {value}")
            await _show_menu(event, settings, state, edit=False)

    @bot_client.on(events.CallbackQuery)
    async def _callbacks(event):
        if not _is_allowed(settings, event.sender_id):
            return
        data = event.data.decode("utf-8") if event.data else ""
        state = state_by_user.setdefault(event.sender_id, BotState())

        if data == "style":
            state.awaiting = "style"
            await event.respond("Введи канал для стиля (username без @).")
            return
        if data == "sources":
            state.awaiting = "sources"
            await event.respond("Введи источники через запятую.")
            return
        if data == "limit":
            state.awaiting = "limit"
            await event.respond("Введи лимит постов на источник (1–50).")
            return
        if data == "run":
            if not state.style_channel:
                await event.respond("Сначала задай канал стиля.")
                return
            if not state.source_channels:
                await event.respond("Сначала задай источники.")
                return
            limit = state.limit or settings.bot_source_limit
            await event.respond("Запускаю. Это может занять 1–2 минуты.")
            await _run_generation(
                event=event,
                settings=settings,
                user_client=user_client,
                brain=brain,
                image_client=image_client,
                state=state,
                limit=limit,
            )
            return
        if data.startswith("copy:"):
            try:
                idx = int(data.split(":", 1)[1])
            except ValueError:
                await event.respond("Не удалось прочитать индекс.")
                return
            if idx < 0 or idx >= len(state.last_posts):
                await event.respond("Этот результат уже недоступен.")
                return
            await event.respond(state.last_posts[idx])
            return
        if data == "repeat":
            if not state.style_channel or not state.source_channels:
                await event.respond("Недостаточно данных для повторного запуска.")
                return
            limit = state.limit or settings.bot_source_limit
            await event.respond("Повторный запуск. Это может занять 1–2 минуты.")
            await _run_generation(
                event=event,
                settings=settings,
                user_client=user_client,
                brain=brain,
                image_client=image_client,
                state=state,
                limit=limit,
            )
            return
        if data == "status":
            await _show_menu(event, settings, state, edit=True)
            return
        if data == "reset":
            state_by_user[event.sender_id] = BotState()
            await event.respond("Настройки сброшены.")
            await _show_menu(event, settings, state_by_user[event.sender_id], edit=True)
            return
        if data == "help":
            await event.respond(_help_text())
            return

        await _show_menu(event, settings, state, edit=True)

    logger.info("Bot is running.")
    try:
        await bot_client.run_until_disconnected()
    finally:
        await bot_client.disconnect()
        await user_client.disconnect()
        if image_client:
            await image_client.aclose()
        await llm_client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        try:
            settings = get_settings()
            send_alert_sync(settings, "cannibal_core.bot", repr(exc))
        except Exception:
            pass
        raise
