"""
Test that search_changed_since does not silently drop memories with id=None.

Refs #770
"""

from unittest.mock import MagicMock, patch


class TestSearchChangedSinceNoneId:
    """Regression tests for the seen_ids dedup bug with None ids."""

    def test_multiple_none_id_memories_not_dropped(self):
        """Memories without an id should NOT be deduplicated against each other.

        Before the fix, the seen_ids set would contain None after the first
        memory with id=None, causing all subsequent id=None memories to be
        silently skipped -- a data loss bug.
        """
        from memanto.app.services.memory_read_service import MemoryReadService

        svc = MemoryReadService.__new__(MemoryReadService)
        svc.moorcheh_client = MagicMock()

        memories_without_ids = [
            {"text": "memory A", "id": None, "created_at": "2026-01-01T12:00:00Z"},
            {"text": "memory B", "id": None, "created_at": "2026-01-01T13:00:00Z"},
            {"text": "memory C", "id": None, "created_at": "2026-01-01T14:00:00Z"},
        ]

        with patch.object(
            svc, "_get_search_namespaces", return_value=["test-ns"]
        ), patch.object(
            svc, "_fetch_all_memories", return_value=memories_without_ids
        ):
            result = svc.search_changed_since(
                since_date="2026-01-01T00:00:00Z",
                agent_id="test-agent",
            )
            assert len(result["results"]) == 3, (
                f"Expected 3 memories, got {len(result['results'])}. "
                "Memories with id=None were silently deduplicated!"
            )

    def test_duplicate_real_ids_still_deduped(self):
        """Real duplicate ids should still be deduplicated."""
        from memanto.app.services.memory_read_service import MemoryReadService

        svc = MemoryReadService.__new__(MemoryReadService)
        svc.moorcheh_client = MagicMock()

        memories = [
            {"text": "memory A", "id": "abc-123", "created_at": "2026-01-01T12:00:00Z"},
            {"text": "memory A (duplicate)", "id": "abc-123", "created_at": "2026-01-01T13:00:00Z"},
            {"text": "memory B", "id": "def-456", "created_at": "2026-01-01T14:00:00Z"},
        ]

        with patch.object(
            svc, "_get_search_namespaces", return_value=["test-ns"]
        ), patch.object(
            svc, "_fetch_all_memories", return_value=memories
        ):
            result = svc.search_changed_since(
                since_date="2026-01-01T00:00:00Z",
                agent_id="test-agent",
            )
            assert len(result["results"]) == 2, (
                f"Expected 2 unique memories, got {len(result['results'])}"
            )
