from __future__ import annotations

from datetime import datetime, timezone

import httpx
from loguru import logger

from .config import Settings


def _resolve_token(settings: Settings) -> str | None:
    return settings.alert_bot_token or settings.bot_token


def _resolve_chat_id(settings: Settings) -> int | None:
    return settings.alert_chat_id


def _format_message(service: str, message: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"⚠️ {service} crashed at {timestamp}\n{message}"


async def send_alert(settings: Settings, service: str, message: str) -> None:
    token = _resolve_token(settings)
    chat_id = _resolve_chat_id(settings)
    if not token or chat_id is None:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": _format_message(service, message)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            await client.post(url, json=payload)
    except Exception:
        logger.exception("Failed to send alert")


def send_alert_sync(settings: Settings, service: str, message: str) -> None:
    token = _resolve_token(settings)
    chat_id = _resolve_chat_id(settings)
    if not token or chat_id is None:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": _format_message(service, message)}
    try:
        httpx.post(url, json=payload, timeout=5.0)
    except Exception:
        logger.exception("Failed to send alert")
