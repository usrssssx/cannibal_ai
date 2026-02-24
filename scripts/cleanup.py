from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import delete, func, select

from cannibal_core.config import get_settings
from cannibal_core.database import Post, WebAppRun, get_session, init_db, init_engine
from cannibal_core.logging_setup import configure_logging
from cannibal_core.vector_store import VectorStore


def _cleanup_logs(logs_dir: Path, cutoff: datetime) -> int:
    removed = 0
    if not logs_dir.exists():
        return removed
    for path in logs_dir.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                logger.warning("Failed to удалить лог {}", path)
    return removed


async def _cleanup_db(retention_days: int, runs_retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    runs_cutoff = datetime.now(timezone.utc) - timedelta(days=runs_retention_days)
    async with get_session() as session:
        posts_count = await session.execute(
            select(func.count(Post.id)).where(Post.created_at < cutoff)
        )
        runs_count = await session.execute(
            select(func.count(WebAppRun.id)).where(WebAppRun.created_at < runs_cutoff)
        )
        await session.execute(delete(Post).where(Post.created_at < cutoff))
        await session.execute(delete(WebAppRun).where(WebAppRun.created_at < runs_cutoff))
        await session.commit()
    logger.info(
        "Cleanup DB: удалено постов={}, запусков={}",
        posts_count.scalar() or 0,
        runs_count.scalar() or 0,
    )


async def _cleanup_vectors(retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    settings = get_settings()
    store = VectorStore(settings)
    await store.delete_older_than(cutoff)


async def main_async(no_vectors: bool) -> None:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    await init_db()

    retention_days = max(1, settings.data_retention_days)
    runs_retention = settings.runs_retention_days or retention_days
    runs_retention = max(1, runs_retention)

    await _cleanup_db(retention_days, runs_retention)
    if not no_vectors:
        await _cleanup_vectors(retention_days)

    logs_days = max(1, settings.logs_cleanup_days)
    logs_cutoff = datetime.now(timezone.utc) - timedelta(days=logs_days)
    removed = _cleanup_logs(Path("logs"), logs_cutoff)
    logger.info("Cleanup logs: удалено файлов={}", removed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup old data and logs")
    parser.add_argument(
        "--no-vectors",
        action="store_true",
        help="Do not cleanup Chroma embeddings",
    )
    args = parser.parse_args()
    asyncio.run(main_async(no_vectors=args.no_vectors))


if __name__ == "__main__":
    main()
