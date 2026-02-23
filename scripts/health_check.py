from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from cannibal_core.config import get_settings


def _session_path(name: str, root: Path) -> Path:
    path = Path(name)
    if not path.suffix:
        path = path.with_suffix(".session")
    if not path.is_absolute():
        path = root / path
    return path


async def _check_ollama(base_url: str, model: str, embed_model: str) -> list[str]:
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            tags = {item.get("name") for item in data.get("models", [])}
            if model not in tags:
                errors.append(f"Ollama model not found: {model}")
            if embed_model not in tags:
                errors.append(f"Ollama embedding model not found: {embed_model}")
    except Exception as exc:
        errors.append(f"Ollama not reachable: {exc}")
    return errors


async def main() -> None:
    settings = get_settings()
    root = Path(__file__).resolve().parents[1]
    issues: list[str] = []

    if settings.enforce_allowed_users and not settings.bot_allowed_users:
        issues.append("BOT_ALLOWED_USERS is empty, but ENFORCE_ALLOWED_USERS=true.")
    elif not settings.bot_allowed_users:
        issues.append("BOT_ALLOWED_USERS is empty (bot/WebApp доступны всем).")

    if settings.webapp_url and not settings.webapp_url.startswith("https://"):
        issues.append("WEBAPP_URL должен быть https.")

    if settings.bot_user_session == settings.telethon_session:
        issues.append("BOT_USER_SESSION совпадает с TELETHON_SESSION.")

    if settings.webapp_user_session == settings.telethon_session:
        issues.append("WEBAPP_USER_SESSION совпадает с TELETHON_SESSION.")

    for name in [
        settings.telethon_session,
        settings.bot_user_session,
        settings.webapp_user_session,
        settings.bot_session,
    ]:
        session_path = _session_path(name, root)
        if not session_path.exists():
            issues.append(f"Session file missing: {session_path}")

    db_path = Path(settings.sqlite_path)
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.exists():
        issues.append(f"SQLite DB not found: {db_path}")

    if settings.llm_provider.lower().strip() == "ollama":
        issues.extend(
            await _check_ollama(
                settings.ollama_base_url,
                settings.ollama_model,
                settings.ollama_embedding_model,
            )
        )
    else:
        if not settings.openai_api_key:
            issues.append("OPENAI_API_KEY is missing.")

    print("Health check")
    if not issues:
        print("OK")
    else:
        print("Warnings:")
        for item in issues:
            print(f"- {item}")


if __name__ == "__main__":
    asyncio.run(main())
