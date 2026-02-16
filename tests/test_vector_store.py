import asyncio
from types import SimpleNamespace

import cannibal_core.vector_store as vector_store_module
from cannibal_core.vector_store import VectorStore


class DummyCollection:
    def __init__(self):
        self.calls = []

    def upsert(self, **payload):
        self.calls.append(payload)


class DummyClient:
    def __init__(self, path):
        self.path = path

    def get_or_create_collection(self, name, metadata):
        return self.collection


def test_vector_store_upsert(monkeypatch):
    collection = DummyCollection()
    client = DummyClient(path=".")
    client.collection = collection

    monkeypatch.setattr(vector_store_module.chromadb, "PersistentClient", lambda path: client)

    settings = SimpleNamespace(chroma_persist_dir=".", chroma_collection="test")
    store = VectorStore(settings)

    asyncio.run(
        store.upsert(
            doc_id="doc-1",
            embedding=[0.1, 0.2],
            document="hello",
            metadata={"k": "v"},
        )
    )

    assert len(collection.calls) == 1
    payload = collection.calls[0]
    assert payload["ids"] == ["doc-1"]
    assert payload["embeddings"] == [[0.1, 0.2]]
    assert payload["documents"] == ["hello"]
    assert payload["metadatas"] == [{"k": "v"}]
