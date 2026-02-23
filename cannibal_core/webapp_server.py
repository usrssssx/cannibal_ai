from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import hashlib
import hmac
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field
from telethon import TelegramClient

from .alerts import send_alert_sync
from .brain import Brain
from .config import get_settings
from sqlalchemy import select

from .database import WebAppRun, WebAppSettings, get_session, init_db, init_engine
from .generation import GenerationError, generate_posts, normalize_channel_ref
from .image_client import ImageClient
from .llm_client import LLMClient
from .logging_setup import configure_logging


WEBAPP_DIR = Path(__file__).resolve().parents[1] / "webapp"


class RunRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData")
    style_channel: str
    sources: list[str]
    limit: int = Field(1, ge=1, le=50)
    with_images: bool = False
    save_settings: bool = True


def _parse_init_data(init_data: str) -> dict[str, str]:
    return dict(parse_qsl(init_data, keep_blank_values=True))


def _verify_init_data(init_data: str, bot_token: str, max_age_sec: int) -> dict[str, Any]:
    data = _parse_init_data(init_data)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if calculated_hash != received_hash:
        raise ValueError("initData hash mismatch")

    auth_date = data.get("auth_date")
    if auth_date:
        if time.time() - int(auth_date) > max_age_sec:
            raise ValueError("initData expired")

    user_raw = data.get("user")
    user = json.loads(user_raw) if user_raw else {}
    data["user"] = user
    return data


def _split_message(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        parts.append(remaining[:limit])
        remaining = remaining[limit:]
    return parts


app = FastAPI(title="Cannibal WebApp")


@app.on_event("startup")
async def _startup() -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to run the WebApp.")
    if settings.enforce_allowed_users and not settings.bot_allowed_users:
        raise RuntimeError("BOT_ALLOWED_USERS is required when ENFORCE_ALLOWED_USERS=true.")
    if not settings.bot_allowed_users:
        logger.warning("BOT_ALLOWED_USERS is empty. WebApp доступен всем пользователям.")
    init_engine(settings)
    await init_db()

    user_client = TelegramClient(
        settings.webapp_user_session or settings.telethon_session,
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )
    await user_client.start()

    llm_client = LLMClient(settings)
    await llm_client.health_check()
    brain = Brain(llm_client, settings)
    image_client = ImageClient(settings) if settings.image_enabled else None

    app.state.settings = settings
    app.state.user_client = user_client
    app.state.brain = brain
    app.state.image_client = image_client
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))


@app.on_event("shutdown")
async def _shutdown() -> None:
    http: httpx.AsyncClient = app.state.http
    await http.aclose()
    user_client: TelegramClient = app.state.user_client
    await user_client.disconnect()


if WEBAPP_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEBAPP_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEBAPP_DIR / "index.html")


@app.post("/api/run")
async def run_generation(payload: RunRequest) -> JSONResponse:
    settings = app.state.settings

    try:
        init_data = _verify_init_data(
            payload.init_data,
            settings.bot_token or "",
            settings.webapp_max_age_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = init_data.get("user") or {}
    user_id = user.get("id")
    if settings.bot_allowed_users and user_id not in settings.bot_allowed_users:
        raise HTTPException(status_code=403, detail="User is not allowed")

    style_channel = normalize_channel_ref(payload.style_channel)
    sources = [normalize_channel_ref(item) for item in payload.sources if item.strip()]
    if not style_channel:
        raise HTTPException(status_code=400, detail="style_channel is empty")
    if not sources:
        raise HTTPException(status_code=400, detail="sources are empty")

    image_client = app.state.image_client if payload.with_images else None
    run_id = await _store_run_start(
        user_id=int(user_id),
        style_channel=style_channel,
        sources=sources,
        limit=payload.limit,
        with_images=payload.with_images,
    )
    if payload.save_settings:
        await _upsert_settings(
            user_id=int(user_id),
            style_channel=style_channel,
            sources=sources,
            limit=payload.limit,
            with_images=payload.with_images,
        )
    try:
        results, errors = await generate_posts(
            settings=settings,
            user_client=app.state.user_client,
            brain=app.state.brain,
            image_client=image_client,
            style_channel=style_channel,
            source_channels=sources,
            limit=payload.limit,
        )
    except GenerationError as exc:
        await _store_run_finish(run_id, status="error", error=exc.message, posts_count=0)
        raise HTTPException(status_code=400, detail=exc.message) from exc

    response_payload = {
        "posts": [
            {
                "source": item.source_channel,
                "message_id": item.message_id,
                "created_at": item.created_at.isoformat(),
                "text": item.rewritten_text,
                "image_url": item.image_url,
                "image_file": item.image_file,
            }
            for item in results
        ],
        "errors": errors,
    }

    if settings.webapp_duplicate_to_chat and user_id:
        await _send_to_chat(
            http=app.state.http,
            bot_token=settings.bot_token or "",
            chat_id=int(user_id),
            payload=response_payload,
        )

    await _store_run_finish(
        run_id,
        status="done",
        error="; ".join(errors) if errors else None,
        posts_count=len(results),
    )

    return JSONResponse(response_payload)


@app.get("/api/settings")
async def get_settings_api(init_data: str) -> JSONResponse:
    settings = app.state.settings
    try:
        init_payload = _verify_init_data(
            init_data,
            settings.bot_token or "",
            settings.webapp_max_age_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = init_payload.get("user") or {}
    user_id = user.get("id")
    if settings.bot_allowed_users and user_id not in settings.bot_allowed_users:
        raise HTTPException(status_code=403, detail="User is not allowed")

    data = await _get_settings(user_id=int(user_id))
    return JSONResponse(data)


@app.get("/api/history")
async def get_history(init_data: str, limit: int = 20) -> JSONResponse:
    settings = app.state.settings
    try:
        init_payload = _verify_init_data(
            init_data,
            settings.bot_token or "",
            settings.webapp_max_age_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = init_payload.get("user") or {}
    user_id = user.get("id")
    if settings.bot_allowed_users and user_id not in settings.bot_allowed_users:
        raise HTTPException(status_code=403, detail="User is not allowed")

    items = await _get_history(user_id=int(user_id), limit=limit)
    return JSONResponse({"items": items})


async def _send_to_chat(
    http: httpx.AsyncClient,
    bot_token: str,
    chat_id: int,
    payload: dict[str, Any],
) -> None:
    if not bot_token:
        return
    posts = payload.get("posts") or []
    errors = payload.get("errors") or []

    for error in errors:
        await _send_message(http, bot_token, chat_id, error)

    for post in posts:
        lines = [
            f"Источник: {post.get('source')}",
            f"Дата: {post.get('created_at')}",
        ]
        if post.get("image_url"):
            lines.append(f"IMAGE_URL: {post.get('image_url')}")
        if post.get("image_file"):
            lines.append(f"IMAGE_FILE: {post.get('image_file')}")
        lines.append(post.get("text") or "")
        text = "\n".join(lines)
        for chunk in _split_message(text):
            await _send_message(http, bot_token, chat_id, chunk)


async def _send_message(
    http: httpx.AsyncClient,
    bot_token: str,
    chat_id: int,
    text: str,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    await http.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
        },
    )


async def _upsert_settings(
    user_id: int,
    style_channel: str,
    sources: list[str],
    limit: int,
    with_images: bool,
) -> None:
    sources_csv = ",".join(sources)
    async with get_session() as session:
        obj = await session.get(WebAppSettings, user_id)
        if obj:
            obj.style_channel = style_channel
            obj.sources_csv = sources_csv
            obj.limit = limit
            obj.with_images = with_images
        else:
            session.add(
                WebAppSettings(
                    user_id=user_id,
                    style_channel=style_channel,
                    sources_csv=sources_csv,
                    limit=limit,
                    with_images=with_images,
                )
            )
        await session.commit()


async def _get_settings(user_id: int) -> dict[str, Any]:
    async with get_session() as session:
        obj = await session.get(WebAppSettings, user_id)
        if not obj:
            return {}
        sources = [part for part in (obj.sources_csv or "").split(",") if part.strip()]
        return {
            "style_channel": obj.style_channel,
            "sources": sources,
            "limit": obj.limit,
            "with_images": obj.with_images,
        }


async def _store_run_start(
    user_id: int,
    style_channel: str,
    sources: list[str],
    limit: int,
    with_images: bool,
) -> int:
    async with get_session() as session:
        run = WebAppRun(
            user_id=user_id,
            style_channel=style_channel,
            sources_csv=",".join(sources),
            limit=limit,
            with_images=with_images,
            status="started",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


async def _store_run_finish(
    run_id: int,
    status: str,
    error: str | None,
    posts_count: int,
) -> None:
    async with get_session() as session:
        run = await session.get(WebAppRun, run_id)
        if not run:
            return
        run.status = status
        run.error = error
        run.posts_count = posts_count
        await session.commit()


async def _get_history(user_id: int, limit: int) -> list[dict[str, Any]]:
    async with get_session() as session:
        stmt = (
            select(WebAppRun)
            .where(WebAppRun.user_id == user_id)
            .order_by(WebAppRun.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        runs = result.scalars().all()
        items: list[dict[str, Any]] = []
        for run in runs:
            items.append(
                {
                    "id": run.id,
                    "style_channel": run.style_channel,
                    "sources": [
                        part
                        for part in (run.sources_csv or "").split(",")
                        if part.strip()
                    ],
                    "limit": run.limit,
                    "with_images": run.with_images,
                    "status": run.status,
                    "error": run.error,
                    "posts_count": run.posts_count,
                    "created_at": run.created_at.isoformat()
                    if run.created_at
                    else None,
                }
            )
        return items


def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    import uvicorn

    try:
        uvicorn.run(
            "cannibal_core.webapp_server:app",
            host=settings.webapp_host,
            port=settings.webapp_port,
            reload=False,
        )
    except Exception as exc:
        send_alert_sync(settings, "cannibal_core.webapp_server", repr(exc))
        raise


if __name__ == "__main__":
    main()
