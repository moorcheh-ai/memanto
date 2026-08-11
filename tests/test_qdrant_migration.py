"""Tests for the Qdrant -> Memanto migration adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memanto.cli.migrate.mappers import MAPPERS, map_qdrant


def _export(memories: list[dict]) -> dict:
    return {"provider": "qdrant", "collection": "memories", "memories": memories}


@pytest.fixture(autouse=True)
def _ensure_registered():
    assert "qdrant" in MAPPERS, "map_qdrant must be registered in MAPPERS"
    yield


def test_map_qdrant_registered():
    assert callable(MAPPERS["qdrant"])


def test_map_qdrant_mem0_style_payload():
    """Mem0-on-Qdrant shape: text + nested metadata dict."""
    export = _export(
        [
            {
                "id": "1",
                "content": "Prefers Python over TypeScript for backend services.",
                "type": "preference",
                "tags": ["language"],
                "created_at": "2026-06-27T04:24:05.875000+00:00",
                "source": "qdrant",
                "payload": {"score": 0.95, "hash": "abc123", "run_id": "run-1"},
                "collection": "memories",
                "has_vector": True,
            }
        ]
    )
    rows = map_qdrant(export)
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "preference"
    assert row["source"] == "qdrant"
    assert row["source_ref"] == "1"
    assert row["provenance"] == "imported"
    assert row["created_at"] is not None
    assert isinstance(row["created_at"], datetime)
    assert "score" in row["content"] and "abc123" in row["content"]
    assert "[Supporting data]" in row["content"]


def test_map_qdrant_langchain_style_payload():
    """LangChain shape: page_content + metadata.tags, type coerced."""
    export = _export(
        [
            {
                "id": "7",
                "content": "Uses VS Code with the Vim extension.",
                "type": None,  # auto-classify on import
                "tags": ["tools"],
                "collection": "memories",
                "payload": {"source": "agent-memory.log"},
                "has_vector": True,
            }
        ]
    )
    rows = map_qdrant(export)
    assert len(rows) == 1
    assert rows[0]["type"] is None  # untyped rows stay untyped (auto-classify)
    assert rows[0]["tags"] == ["tools"]
    assert "agent-memory.log" in rows[0]["content"]


def test_map_qdrant_skips_empty_content():
    export = _export([{"id": "2", "content": "   ", "type": None, "tags": []}])
    assert map_qdrant(export) == []


def test_map_qdrant_type_coercion_only_valid_types():
    """Invalid/missing payload types are dropped, not invented."""
    export = _export(
        [
            {
                "id": "3",
                "content": "A genuine memory worth keeping.",
                "type": "not-a-real-memanto-type",
                "tags": [],
            }
        ]
    )
    rows = map_qdrant(export)
    assert len(rows) == 1
    assert rows[0]["type"] is None


def test_map_qdrant_preserves_timestamp_via_ms_epoch():
    """Millisecond epoch timestamps surface as real datetimes."""
    export = _export(
        [
            {
                "id": "4",
                "content": "Seeded memory with ms epoch.",
                "type": "fact",
                "tags": [],
                "created_at": "2026-07-01T00:00:00+00:00",
            }
        ]
    )
    row = map_qdrant(export)[0]
    assert row["created_at"] == datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_qdrant_export_dump_collection_in_memory():
    """End-to-end: seed an embedded Qdrant, dump it, map it."""
    qdrant_client = pytest.importorskip("qdrant_client")
    from qdrant_client.models import Distance, PointStruct, VectorParams

    from memanto.cli.analyze.qdrant_export import dump_collection

    client = qdrant_client.QdrantClient(":memory:")
    client.create_collection(
        collection_name="memories",
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    client.upsert(
        collection_name="memories",
        points=[
            PointStruct(
                id=1,
                vector=[0.1, 0.2, 0.3, 0.4],
                payload={
                    "text": "Lives in Lisbon, Portugal.",
                    "metadata": {
                        "created_at": 1719900000000,
                        "memory_type": "fact",
                        "user_id": "tim",
                    },
                },
            )
        ],
    )
    memories = dump_collection(client, "memories")
    assert len(memories) == 1
    assert memories[0]["content"] == "Lives in Lisbon, Portugal."
    assert memories[0]["type"] == "fact"

    rows = map_qdrant({"provider": "qdrant", "memories": memories})
    assert len(rows) == 1
    assert rows[0]["type"] == "fact"
    assert "qdrant:1" in rows[0]["content"]
