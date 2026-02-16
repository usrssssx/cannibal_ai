import asyncio

from sqlalchemy import select

from cannibal_core.config import Settings
from cannibal_core.database import Post, get_session, init_db, init_engine
from cannibal_core.deduplicator import DedupResult
from cannibal_core.processor import Processor


class FakeDeduplicator:
    def __init__(self, result: DedupResult) -> None:
        self.result = result
        self.calls = 0

    async def check(self, text: str) -> DedupResult:
        self.calls += 1
        return self.result


class FakeBrain:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls = 0

    async def generate(self, text: str, style_profile: str | None = None) -> str:
        self.calls += 1
        return self.output


class FakeVectorStore:
    def __init__(self) -> None:
        self.add_calls = []

    async def add(self, doc_id, embedding, document, metadata) -> None:
        self.add_calls.append(
            {
                "doc_id": doc_id,
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }
        )


def _build_settings(tmp_path) -> Settings:
    return Settings(
        telethon_api_id=1,
        telethon_api_hash="hash",
        sqlite_path=str(tmp_path / "test.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
        output_path=str(tmp_path / "out.txt"),
    )


def _fetch_single_post():
    async def _run():
        async with get_session() as session:
            result = await session.execute(select(Post))
            return result.scalar_one()

    return asyncio.run(_run())


def test_processor_unique_writes_output_and_updates_db(tmp_path):
    settings = _build_settings(tmp_path)
    init_engine(settings)
    asyncio.run(init_db())

    dedup = FakeDeduplicator(
        DedupResult(
            is_duplicate=False,
            similarity=0.9,
            matched_id=None,
            embedding=[0.1, 0.2],
        )
    )
    brain = FakeBrain("rewritten")
    store = FakeVectorStore()
    processor = Processor(settings, dedup, brain, store, style_profiles=None)

    asyncio.run(
        processor.handle_message(
            channel_name="channel",
            channel_id=123,
            message_id=7,
            text="hello world",
        )
    )

    output_path = tmp_path / "out.txt"
    assert output_path.exists()
    assert "rewritten" in output_path.read_text(encoding="utf-8")

    post = _fetch_single_post()
    assert post.rewritten_text == "rewritten"
    assert post.is_duplicate is False
    assert post.processed_at is not None
    assert post.similarity == 0.9

    assert len(store.add_calls) == 1
    assert brain.calls == 1
    assert dedup.calls == 1


def test_processor_duplicate_marks_db_and_skips_output(tmp_path):
    settings = _build_settings(tmp_path)
    init_engine(settings)
    asyncio.run(init_db())

    dedup = FakeDeduplicator(
        DedupResult(
            is_duplicate=True,
            similarity=0.95,
            matched_id="doc-1",
            embedding=[0.1, 0.2],
        )
    )
    brain = FakeBrain("rewritten")
    store = FakeVectorStore()
    processor = Processor(settings, dedup, brain, store, style_profiles=None)

    asyncio.run(
        processor.handle_message(
            channel_name="channel",
            channel_id=123,
            message_id=8,
            text="hello world",
        )
    )

    output_path = tmp_path / "out.txt"
    assert not output_path.exists()

    post = _fetch_single_post()
    assert post.is_duplicate is True
    assert post.duplicate_of == "doc-1"
    assert post.rewritten_text is None
    assert post.processed_at is not None

    assert store.add_calls == []
    assert brain.calls == 0
    assert dedup.calls == 1


def test_processor_skips_already_processed(tmp_path):
    settings = _build_settings(tmp_path)
    init_engine(settings)
    asyncio.run(init_db())

    dedup = FakeDeduplicator(
        DedupResult(
            is_duplicate=False,
            similarity=0.5,
            matched_id=None,
            embedding=[0.1, 0.2],
        )
    )
    brain = FakeBrain("rewritten")
    store = FakeVectorStore()
    processor = Processor(settings, dedup, brain, store, style_profiles=None)

    asyncio.run(
        processor.handle_message(
            channel_name="channel",
            channel_id=123,
            message_id=9,
            text="hello world",
        )
    )
    asyncio.run(
        processor.handle_message(
            channel_name="channel",
            channel_id=123,
            message_id=9,
            text="hello world",
        )
    )

    output_path = tmp_path / "out.txt"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert content.count("rewritten") == 1
    assert dedup.calls == 1
    assert brain.calls == 1
