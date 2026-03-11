import asyncio
import sqlite3

from cannibal_core.config import Settings
from cannibal_core.database import init_db, init_engine


def _build_settings(tmp_path) -> Settings:
    return Settings(
        telethon_api_id=1,
        telethon_api_hash="hash",
        sqlite_path=str(tmp_path / "test.db"),
    )


def _load_tables(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in rows.fetchall()}


def test_init_db_runs_alembic_migrations(tmp_path):
    settings = _build_settings(tmp_path)
    init_engine(settings)

    asyncio.run(init_db())
    asyncio.run(init_db())

    tables = _load_tables(tmp_path / "test.db")
    assert "alembic_version" in tables
    assert "channels" in tables
    assert "posts" in tables
    assert "webapp_runs" in tables
    assert "editorial_sources" in tables
    assert "editorial_source_posts" in tables
    assert "editorial_topic_reports" in tables
    assert "editorial_topics" in tables
    assert "editorial_topic_posts" in tables
    assert "editorial_generation_runs" in tables
    assert "editorial_generation_outputs" in tables
