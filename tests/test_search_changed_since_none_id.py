"""
Test that search_changed_since does not silently drop memories with id=None.

Refs #770
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSearchChangedSinceNoneId:
    """Regression tests for the seen_ids dedup bug with None ids."""

    @pytest.mark.asyncio
    async def test_multiple_none_id_memories_not_dropped(self):
        """Memories without an id should NOT be deduplicated against each other.

        Before the fix, the seen_ids set would contain None after the first
        memory with id=None, causing all subsequent id=None memories to be
        silently skipped -- a data loss bug.
        """
        from memanto.app.services.memory_read_service import MemoryReadService

        svc = MemoryReadService.__new__(MemoryReadService)
        svc.moorcheh_client = AsyncMock()
        svc.config = MagicMock()
        svc.config.moorcheh_api_key = "test-key"
        svc.config.moorcheh_namespace = "test-ns"

        memories_without_ids = [
            {"text": "memory A", "id": None},
            {"text": "memory B", "id": None},
            {"text": "memory C", "id": None},
        ]

        with patch.object(
            svc, "_search_all_namespaces", return_value=memories_without_ids
        ), patch.object(
            svc, "_format_memory_item", side_effect=lambda m, ns: {**m, "namespace": ns}
        ):
            result = await svc.search_changed_since(
                agent_id="test-agent",
                since="2026-01-01T00:00:00Z",
            )
            assert len(result) == 3, (
                f"Expected 3 memories, got {len(result)}. "
                "Memories with id=None were silently deduplicated!"
            )

    @pytest.mark.asyncio
    async def test_duplicate_real_ids_still_deduped(self):
        """Real duplicate ids should still be deduplicated."""
        from memanto.app.services.memory_read_service import MemoryReadService

        svc = MemoryReadService.__new__(MemoryReadService)
        svc.moorcheh_client = AsyncMock()
        svc.config = MagicMock()
        svc.config.moorcheh_api_key = "test-key"
        svc.config.moorcheh_namespace = "test-ns"

        memories = [
            {"text": "memory A", "id": "abc-123"},
            {"text": "memory A (duplicate)", "id": "abc-123"},
            {"text": "memory B", "id": "def-456"},
        ]

        with patch.object(
            svc, "_search_all_namespaces", return_value=memories
        ), patch.object(
            svc, "_format_memory_item", side_effect=lambda m, ns: {**m, "namespace": ns}
        ):
            result = await svc.search_changed_since(
                agent_id="test-agent",
                since="2026-01-01T00:00:00Z",
            )
            assert len(result) == 2, (
                f"Expected 2 unique memories, got {len(result)}"
            )
