import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import cannibal_core.backfill as backfill


class FakeMessage:
    def __init__(self, message_id: int, text: str, date: datetime | None) -> None:
        self.id = message_id
        self.message = text
        self.date = date


class FakeClient:
    def __init__(self, entity, messages):
        self._entity = entity
        self._messages = messages

    async def get_entity(self, channel_ref):
        return self._entity

    async def iter_messages(self, entity, limit: int):
        for msg in self._messages[:limit]:
            yield msg


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def embed(self, text: str):
        self.calls.append(text)
        return [0.1, 0.2]


class FakeVectorStore:
    def __init__(self):
        self.calls = []

    async def upsert(self, doc_id, embedding, document, metadata):
        self.calls.append(
            {
                "doc_id": doc_id,
                "embedding": embedding,
                "document": document,
                "metadata": metadata,
            }
        )


def test_backfill_channel_with_embeddings(monkeypatch):
    stored_posts = []

    async def fake_get_or_create_channel(name, channel_id):
        return SimpleNamespace(id=777)

    async def fake_store_post(channel_db_id, message_id, text):
        stored_posts.append((channel_db_id, message_id, text))

    monkeypatch.setattr(backfill, "_get_or_create_channel", fake_get_or_create_channel)
    monkeypatch.setattr(backfill, "_store_post", fake_store_post)

    entity = SimpleNamespace(id=99, username="channel_one", title=None)
    dt = datetime(2024, 1, 1, 12, 0, 0)
    messages = [
        FakeMessage(1, "реклама супер", dt),
        FakeMessage(2, "   ", dt),
        FakeMessage(3, "A" * 15, dt),
    ]
    client = FakeClient(entity, messages)
    llm = FakeLLM()
    vector_store = FakeVectorStore()

    asyncio.run(
        backfill._backfill_channel(
            client=client,
            llm_client=llm,
            vector_store=vector_store,
            channel_ref="channel_one",
            limit=10,
            stop_words=["реклама"],
            max_chars=10,
            store_embeddings=True,
        )
    )

    assert stored_posts == [(777, 3, "A" * 10)]
    assert llm.calls == ["A" * 10]
    assert len(vector_store.calls) == 1
    call = vector_store.calls[0]
    assert call["doc_id"] == "99:3"
    assert call["document"] == "A" * 10
    assert call["metadata"]["channel"] == "channel_one"
    assert call["metadata"]["channel_id"] == 99
    assert call["metadata"]["message_id"] == 3

    expected_ts = dt.replace(tzinfo=timezone.utc).timestamp()
    assert call["metadata"]["created_at"] == expected_ts


def test_backfill_channel_without_embeddings(monkeypatch):
    stored_posts = []

    async def fake_get_or_create_channel(name, channel_id):
        return SimpleNamespace(id=321)

    async def fake_store_post(channel_db_id, message_id, text):
        stored_posts.append((channel_db_id, message_id, text))

    monkeypatch.setattr(backfill, "_get_or_create_channel", fake_get_or_create_channel)
    monkeypatch.setattr(backfill, "_store_post", fake_store_post)

    entity = SimpleNamespace(id=55, username="channel_two", title=None)
    dt = datetime(2024, 2, 1, 9, 0, 0, tzinfo=timezone.utc)
    messages = [FakeMessage(9, "Hello world", dt)]
    client = FakeClient(entity, messages)
    llm = FakeLLM()
    vector_store = FakeVectorStore()

    asyncio.run(
        backfill._backfill_channel(
            client=client,
            llm_client=llm,
            vector_store=vector_store,
            channel_ref="channel_two",
            limit=10,
            stop_words=[],
            max_chars=100,
            store_embeddings=False,
        )
    )

    assert stored_posts == [(321, 9, "Hello world")]
    assert llm.calls == []
    assert vector_store.calls == []
