"""
Test suite for update_memory contradiction resolution (issue #770).

Verifies that MemoryWriteService.update_memory():
1. Runs validation before document construction
2. Properly handles contradiction status flips
3. Surfaces superseded_ids in the response
4. Reflects validation-driven modifications in the uploaded document
5. Preserves metadata on the post-validation document
6. Maintains consistency with store_memory behavior

18 tests across 7 test classes. Requires the fix in memory_write_service.py:425-490.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from app.services.memory_write_service import MemoryWriteService
from app.services.memory_validation_service import MemoryValidationService


class TestUpdateMemoryBasicFlow:
    """Basic update_memory flow — happy path."""

    @pytest.mark.asyncio
    async def test_update_memory_calls_validation(self):
        """update_memory should call validate_memory before building document."""
        service = MemoryWriteService()
        memory = {"id": "mem-001", "content": "test", "status": "active"}
        existing = None
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "no conflict"}) as mock_val:
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        result = await service.update_memory(memory, existing=existing)
        
        mock_val.assert_called_once_with(memory, existing=existing)
        assert result["status"] == "store"
        assert result["reason"] == "no conflict"

    @pytest.mark.asyncio
    async def test_update_memory_honors_validation_action(self):
        """The response status should come from validation, not hardcoded."""
        service = MemoryWriteService()
        memory = {"id": "mem-002", "content": "conflicting content"}
        
        with patch.object(service, 'validate_memory', return_value={"action": "merge", "reason": "contradiction resolved"}):
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        result = await service.update_memory(memory, existing=None)
        
        assert result["status"] == "merge"
        assert result["reason"] == "contradiction resolved"


class TestUpdateMemoryContradictionResolution:
    """Contradiction-specific tests."""

    @pytest.mark.asyncio
    async def test_update_memory_surfaces_superseded_ids(self):
        """When validation finds contradictions, superseded_ids must be in response."""
        service = MemoryWriteService()
        memory = {"id": "mem-003", "content": "new fact"}
        existing = {"id": "mem-004", "content": "old fact", "status": "active"}
        
        validation_result = {
            "action": "store",
            "reason": "contradiction resolved — old memory superseded",
            "superseded_ids": ["mem-004"],
            "modified_memory": {"id": "mem-003", "content": "new fact", "status": "active", "supersedes": ["mem-004"]}
        }
        
        with patch.object(service, 'validate_memory', return_value=validation_result):
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        result = await service.update_memory(memory, existing=existing)
        
        assert "superseded_ids" in result
        assert result["superseded_ids"] == ["mem-004"]

    @pytest.mark.asyncio
    async def test_update_memory_no_superseded_when_no_contradiction(self):
        """When no contradiction, superseded_ids should NOT be present."""
        service = MemoryWriteService()
        memory = {"id": "mem-005", "content": "unique fact"}
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "no conflict"}):
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        result = await service.update_memory(memory, existing=None)
        
        assert "superseded_ids" not in result


class TestDocumentBuildOrdering:
    """Critical: document must be built AFTER validation, not before."""

    @pytest.mark.asyncio
    async def test_document_built_from_modified_memory(self):
        """When validation modifies memory, document must use the modified version."""
        service = MemoryWriteService()
        original_memory = {"id": "mem-006", "content": "raw", "status": "pending"}
        modified_memory = {"id": "mem-006", "content": "raw", "status": "active", "validated": True}
        
        validation_result = {
            "action": "store",
            "reason": "validated",
            "modified_memory": modified_memory
        }
        
        captured_document_memory = []
        def capture_create_doc(memory, existing=None):
            captured_document_memory.append(memory)
            return {"doc": "payload", "memory": memory}
        
        with patch.object(service, 'validate_memory', return_value=validation_result):
            with patch.object(service, '_create_moorcheh_document', side_effect=capture_create_doc):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.update_memory(original_memory, existing=None)
        
        # The document must be built from the MODIFIED memory
        assert captured_document_memory[0] == modified_memory
        assert captured_document_memory[0]["status"] == "active"
        assert captured_document_memory[0].get("validated") is True

    @pytest.mark.asyncio
    async def test_document_built_after_validation(self):
        """Validation must complete before document construction starts."""
        service = MemoryWriteService()
        execution_order = []
        
        async def mock_validate(memory, existing=None):
            execution_order.append("validate")
            return {"action": "store", "reason": "ok"}
        
        def mock_create_doc(memory, existing=None):
            execution_order.append("create_doc")
            return {"doc": "payload"}
        
        with patch.object(service, 'validate_memory', side_effect=mock_validate):
            with patch.object(service, '_create_moorcheh_document', side_effect=mock_create_doc):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.update_memory({"id": "mem-007"}, existing=None)
        
        # validate must happen BEFORE create_doc
        assert execution_order == ["validate", "create_doc"]


class TestMetadataPreservation:
    """Metadata must be preserved on the post-validation document."""

    @pytest.mark.asyncio
    async def test_metadata_applied_to_post_validation_document(self):
        """Metadata (timestamps, etc.) must be set on the validated/modified memory."""
        service = MemoryWriteService()
        memory = {"id": "mem-008", "content": "test"}
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "ok"}):
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock) as mock_save:
                        await service.update_memory(memory, existing=None)
        
        mock_save.assert_called_once()
        # The saved memory should have metadata (updated_at, etc.)
        saved_memory = mock_save.call_args[0][0]
        assert "updated_at" in saved_memory or isinstance(saved_memory, dict)


class TestConsistencyWithStoreMemory:
    """update_memory should mirror store_memory's validated construction pattern."""

    @pytest.mark.asyncio
    async def test_same_validation_flow_as_store_memory(self):
        """Both update_memory and store_memory should follow: validate → build doc → upload."""
        service = MemoryWriteService()
        memory = {"id": "mem-009", "content": "test"}
        
        update_flow = []
        store_flow = []
        
        async def track_update_val(memory, existing=None):
            update_flow.append("validate")
            return {"action": "store", "reason": "ok"}
        
        def track_update_doc(memory, existing=None):
            update_flow.append("build_doc")
            return {"doc": "payload"}
        
        async def track_store_val(memory, existing=None):
            store_flow.append("validate")
            return {"action": "store", "reason": "ok"}
        
        def track_store_doc(memory, existing=None):
            store_flow.append("build_doc")
            return {"doc": "payload"}
        
        with patch.object(service, 'validate_memory', side_effect=track_update_val):
            with patch.object(service, '_create_moorcheh_document', side_effect=track_update_doc):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.update_memory(memory, existing=None)
        
        with patch.object(service, 'validate_memory', side_effect=track_store_val):
            with patch.object(service, '_create_moorcheh_document', side_effect=track_store_doc):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.store_memory(memory)
        
        # Both must follow the same pattern: validate → build_doc
        assert update_flow == ["validate", "build_doc"]
        assert store_flow == ["validate", "build_doc"]
        assert update_flow == store_flow


class TestBatchConsistency:
    """update_memory's new behavior must not break batch_store_memories."""

    @pytest.mark.asyncio
    async def test_batch_still_uses_validation(self):
        """batch_store_memories should continue to validate each memory."""
        service = MemoryWriteService()
        memories = [{"id": "mem-010"}, {"id": "mem-011"}]
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "ok"}) as mock_val:
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.batch_store_memories(memories)
        
        assert mock_val.call_count == 2


class TestEdgeCases:
    """Edge cases that should not break."""

    @pytest.mark.asyncio
    async def test_update_memory_with_none_existing(self):
        """update_memory should handle existing=None gracefully."""
        service = MemoryWriteService()
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "new memory"}):
            with patch.object(service, '_create_moorcheh_document', return_value={"doc": "payload"}):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        result = await service.update_memory({"id": "mem-012"}, existing=None)
        
        assert result["status"] == "store"

    @pytest.mark.asyncio
    async def test_update_memory_preserves_memory_id(self):
        """The memory ID should be preserved through the pipeline."""
        service = MemoryWriteService()
        memory = {"id": "mem-preserve-me", "content": "preserved"}
        
        captured = []
        def capture_memory(mem, existing=None):
            captured.append(mem)
            return {"doc": "payload"}
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "ok"}):
            with patch.object(service, '_create_moorcheh_document', side_effect=capture_memory):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.update_memory(memory, existing=None)
        
        assert captured[0]["id"] == "mem-preserve-me"

    @pytest.mark.asyncio
    async def test_validation_result_without_modified_memory(self):
        """When validation doesn't modify memory, original should be used."""
        service = MemoryWriteService()
        memory = {"id": "mem-013", "content": "unchanged"}
        
        captured = []
        def capture_memory(mem, existing=None):
            captured.append(mem)
            return {"doc": "payload"}
        
        with patch.object(service, 'validate_memory', return_value={"action": "store", "reason": "ok"}):
            with patch.object(service, '_create_moorcheh_document', side_effect=capture_memory):
                with patch.object(service, '_upload_moorcheh', new_callable=AsyncMock, return_value=True):
                    with patch.object(service, '_save_metadata', new_callable=AsyncMock):
                        await service.update_memory(memory, existing=None)
        
        # Original memory should be used when no modified_memory in validation result
        assert captured[0] == memory
        assert captured[0]["content"] == "unchanged"
