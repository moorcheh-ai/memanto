"""Test that search_changed_since does not silently drop memories with None id.

Reproduces the data-loss bug fixed in this branch: memories without an id
were deduplicated as if they were the same memory, causing all but the
first id-less memory to be silently dropped.

Refs #770
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_memory(memory_id, content, created_at="2025-12-01T10:00:00Z", updated_at=None):
    """Build a memory dict matching the format returned by _format_memory_item."""
    m = {
        "id": memory_id,
        "title": content[:40],
        "content": content,
        "type": "fact",
        "confidence": 0.8,
        "status": "active",
        "created_at": created_at,
        "updated_at": updated_at or created_at,
        "score": 0.9,
    }
    return m


class TestSearchChangedSinceNoneIdDedup:
    """search_changed_since must not treat memories with missing ids as duplicates."""

    def test_multiple_none_id_memories_are_all_kept(self):
        """All memories with id=None should appear in results, not just the first."""
        from memanto.app.services.memory_read_service import MemoryReadService

        client = MagicMock()
        service = MemoryReadService(client)

        # Patch _fetch_all_memories to return memories with None ids
        memories = [
            _make_memory(None, "Memory A"),
            _make_memory(None, "Memory B"),
            _make_memory("abc-123", "Memory C"),
            _make_memory(None, "Memory D"),
        ]

        with patch.object(service, "_fetch_all_memories", return_value=memories):
            result = service.search_changed_since(
                since_date="2025-11-01T00:00:00Z",
                agent_id="test-agent",
            )

        returned_contents = [m["content"] for m in result["results"]]
        # All four memories must be present (no silent drops)
        assert "Memory A" in returned_contents
        assert "Memory B" in returned_contents
        assert "Memory C" in returned_contents
        assert "Memory D" in returned_contents
        assert result["total_found"] == 4

    def test_real_id_dedup_still_works(self):
        """Memories with the same real id should still be deduplicated."""
        from memanto.app.services.memory_read_service import MemoryReadService

        client = MagicMock()
        service = MemoryReadService(client)

        memories = [
            _make_memory("dup-id", "First version"),
            _make_memory("dup-id", "Second version"),
            _make_memory("unique-id", "Unique memory"),
        ]

        with patch.object(service, "_fetch_all_memories", return_value=memories):
            result = service.search_changed_since(
                since_date="2025-11-01T00:00:00Z",
                agent_id="test-agent",
            )

        # Only 2 unique ids: dup-id (first occurrence kept) + unique-id
        assert result["total_found"] == 2
        returned_ids = [m["id"] for m in result["results"]]
        assert "dup-id" in returned_ids
        assert "unique-id" in returned_ids

    def test_mixed_none_and_real_ids(self):
        """Mix of None and real ids: each None-id memory is kept, real ids dedup."""
        from memanto.app.services.memory_read_service import MemoryReadService

        client = MagicMock()
        service = MemoryReadService(client)

        memories = [
            _make_memory(None, "No-id A"),
            _make_memory("real-1", "Real 1"),
            _make_memory(None, "No-id B"),
            _make_memory("real-1", "Real 1 dup"),
            _make_memory(None, "No-id C"),
        ]

        with patch.object(service, "_fetch_all_memories", return_value=memories):
            result = service.search_changed_since(
                since_date="2025-11-01T00:00:00Z",
                agent_id="test-agent",
            )

        # 3 None-id + 1 unique real id = 4
        assert result["total_found"] == 4
        contents = [m["content"] for m in result["results"]]
        assert "No-id A" in contents
        assert "No-id B" in contents
        assert "No-id C" in contents
        assert "Real 1" in contents
