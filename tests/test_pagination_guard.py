"""Regression tests for memory document pagination."""

from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService


def test_fetch_all_memories_stops_on_repeated_next_token():
    """A stuck backend cursor must not keep a read request looping forever."""
    page = {
        "items": [
            {
                "id": "memory-1",
                "text": "[FACT] Repeated page",
                "metadata": {},
            }
        ],
        "pagination": {"has_more": True, "next_token": "stuck-token"},
    }
    client = MagicMock()
    client.documents.fetch_text_data.side_effect = [
        page,
        page,
        AssertionError("repeated cursor triggered another request"),
    ]

    memories = MemoryReadService(client)._fetch_all_memories(["test-namespace"])

    assert [memory["id"] for memory in memories] == ["memory-1"]
    assert client.documents.fetch_text_data.call_count == 2
