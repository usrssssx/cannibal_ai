import asyncio
from types import SimpleNamespace

from sqlalchemy import select

from cannibal_core.config import Settings
from cannibal_core.database import EditorialSource, get_session, init_db, init_engine
from cannibal_core.editorial import (
    list_editorial_sources,
    resolve_editorial_source,
    upsert_editorial_sources,
)


def _build_settings(tmp_path) -> Settings:
    return Settings(
        telethon_api_id=1,
        telethon_api_hash="hash",
        sqlite_path=str(tmp_path / "test.db"),
    )


def test_resolve_editorial_source_accepts_numeric_ref() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.raw_ref = None

        async def get_entity(self, raw_ref):
            self.raw_ref = raw_ref
            return SimpleNamespace(id=777, username=None, title="Private channel")

    client = FakeClient()

    result = asyncio.run(resolve_editorial_source(client, 777))

    assert client.raw_ref == 777
    assert result == {
        "channel_ref": "777",
        "channel_title": "Private channel",
        "telegram_id": 777,
        "added_via": "manual",
    }


def test_upsert_editorial_sources_replace_marks_missing_inactive(tmp_path) -> None:
    settings = _build_settings(tmp_path)
    init_engine(settings)
    asyncio.run(init_db())

    async def scenario():
        await upsert_editorial_sources(
            42,
            [
                {
                    "channel_ref": "one",
                    "channel_title": "One",
                    "telegram_id": 1,
                    "added_via": "manual",
                },
                {
                    "channel_ref": "two",
                    "channel_title": "Two",
                    "telegram_id": 2,
                    "added_via": "manual",
                },
            ],
        )
        await upsert_editorial_sources(
            42,
            [
                {
                    "channel_ref": "two",
                    "channel_title": "Two v2",
                    "telegram_id": 2,
                    "added_via": "forward",
                }
            ],
            replace=True,
        )

        active_sources = await list_editorial_sources(42)
        async with get_session() as session:
            result = await session.execute(
                select(EditorialSource).order_by(EditorialSource.channel_ref.asc())
            )
            rows = result.scalars().all()
        return active_sources, rows

    active_sources, rows = asyncio.run(scenario())

    assert active_sources == [
        {
            "id": active_sources[0]["id"],
            "channel_ref": "two",
            "channel_title": "Two v2",
            "telegram_id": 2,
            "added_via": "forward",
        }
    ]
    assert [(row.channel_ref, row.is_active) for row in rows] == [
        ("one", False),
        ("two", True),
    ]
