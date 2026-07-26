"""
Test suite for update_memory contradiction resolution (issue #770).

Verifies that MemoryWriteService.update_memory():
1. Runs validation before document construction (bug fix: no more MVP direct store)
2. Properly handles contradiction status flips
3. Surfaces superseded_ids in the response
4. Reflects validation-driven modifications in the uploaded document
5. Preserves metadata on the post-validation document
6. Maintains consistency with store_memory behavior

18 tests across 7 test classes.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_validation_service import MemoryValidationService
from memanto.app.services.memory_read_service import MemoryReadService


def make_client(upload_result=None):
    """Create a mock MoorchehClient with default success responses."""
    client = MagicMock()
    client.documents.upload.return_value = upload_result or {"status": "success"}
    client.documents.delete.return_value = {"actual_deletions": 1}
    client.similarity_search.query.return_value = {"results": []}
    return client


def existing_doc(memory_id="old-1", title="Test", content="old content", agent_id="test-agent", status="active"):
    """Return a dict matching what MemoryReadService.get_memory returns."""
    return {
        "id": memory_id,
        "text": f"[FACT] {title}\n\n{content}",
        "title": title,
        "content": content,
        "type": "fact",
        "status": status,
        "agent_id": agent_id,
        "actor_id": "user",
        "source": "user",
        "confidence": 0.8,
        "metadata": {
            "agent_id": agent_id,
            "actor_id": "user",
            "type": "fact",
            "confidence": 0.8,
            "created_at": "2026-01-01T00:00:00",
        },
    }


def make_memory(memory_id="mem-new", content="new content", **overrides):
    """Build a MemoryRecord for validation_result['memory'] payloads."""
    defaults = {
        "id": memory_id,
        "content": content,
        "type": "fact",
        "title": "Test",
        "agent_id": "test-agent",
        "actor_id": "user",
        "source": "user",
    }
    defaults.update(overrides)
    return MemoryRecord(**defaults)


class TestUpdateMemoryBasicFlow:
    """Basic update_memory flow — happy path."""

    def test_update_memory_calls_validation(self):
        """update_memory should call validate_memory before building document."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "no conflict"}
            ) as mock_val:
                result = service.update_memory(
                    "mem-001", "memanto_agent_test-agent",
                    {"content": "new content"}, context=None
                )

        mock_val.assert_called_once()
        # Assert action (not status) per CodeRabbit feedback
        assert result["action"] == "store"
        assert result["reason"] == "no conflict"

    def test_update_memory_honors_validation_action(self):
        """The response action should come from validation, not hardcoded."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "merge", "reason": "contradiction resolved"}
            ):
                result = service.update_memory(
                    "mem-002", "memanto_agent_test-agent",
                    {"content": "conflicting content"}, context=None
                )

        assert result["action"] == "merge"
        assert result["reason"] == "contradiction resolved"


class TestUpdateMemoryContradictionResolution:
    """Contradiction-specific tests."""

    def test_update_memory_surfaces_superseded_ids(self):
        """When validation finds contradictions, superseded_ids must be in response."""
        client = make_client()
        service = MemoryWriteService(client)

        validation_result = {
            "action": "store",
            "reason": "contradiction resolved — old memory superseded",
            "superseded_ids": ["mem-004"],
            "memory": make_memory(
                memory_id="mem-003", content="new fact",
            ),
        }

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc("mem-004")):
            with patch.object(service.validation_service, "validate_memory",
                              return_value=validation_result):
                result = service.update_memory(
                    "mem-003", "memanto_agent_test-agent",
                    {"content": "new fact"}, context=None
                )

        assert "superseded_ids" in result
        assert result["superseded_ids"] == ["mem-004"]

    def test_update_memory_no_superseded_when_no_contradiction(self):
        """When no contradiction, superseded_ids should NOT be present."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "no conflict"}
            ):
                result = service.update_memory(
                    "mem-005", "memanto_agent_test-agent",
                    {"content": "unique fact"}, context=None
                )

        assert "superseded_ids" not in result


class TestDocumentBuildOrdering:
    """Critical: document must be built AFTER validation, not before."""

    def test_document_built_from_modified_memory(self):
        """When validation modifies memory, document must use the modified version."""
        client = make_client()
        service = MemoryWriteService(client)

        modified_memory = make_memory(
            memory_id="mem-006", content="raw", status="active",
        )

        validation_result = {
            "action": "store",
            "reason": "validated",
            "memory": modified_memory,
        }

        with patch.object(MemoryReadService, "get_memory",
                          return_value=existing_doc("mem-006", status="pending")):
            with patch.object(service.validation_service, "validate_memory",
                              return_value=validation_result):
                service.update_memory(
                    "mem-006", "memanto_agent_test-agent",
                    {"content": "raw"}, context=None
                )

        # The uploaded document must use the modified memory (status="active")
        upload_call = client.documents.upload.call_args
        uploaded_doc = upload_call.kwargs["documents"][0]
        assert uploaded_doc["id"] == "mem-006"
        assert uploaded_doc["status"] == "active", (
            "Document was NOT rebuilt from the modified memory"
        )

    def test_document_built_after_validation(self):
        """Validation must complete before document construction starts."""
        client = make_client()
        service = MemoryWriteService(client)
        execution_order = []

        def mock_validate(memory, context=None):
            execution_order.append("validate")
            return {"action": "store", "reason": "ok"}

        with patch.object(MemoryReadService, "get_memory",
                          return_value=existing_doc()):
            with patch.object(service.validation_service, "validate_memory",
                              side_effect=mock_validate):
                with patch.object(client.documents, "upload",
                                  return_value={"status": "success"}) as mock_upload:
                    def track_upload(*args, **kwargs):
                        execution_order.append("upload")
                        return {"status": "success"}
                    mock_upload.side_effect = track_upload
                    service.update_memory(
                        "mem-007", "memanto_agent_test-agent",
                        {"content": "test"}, context=None
                    )

        # validate must happen BEFORE upload (document construction)
        assert execution_order == ["validate", "upload"]


class TestMetadataPreservation:
    """Metadata must be preserved on the post-validation document."""

    def test_metadata_applied_to_post_validation_document(self):
        """Metadata (timestamps, agent_id) must be present in the uploaded document."""
        client = make_client()
        service = MemoryWriteService(client)

        existing = existing_doc("mem-008", content="original", agent_id="test-agent")

        with patch.object(MemoryReadService, "get_memory", return_value=existing):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ):
                service.update_memory(
                    "mem-008", "memanto_agent_test-agent",
                    {"content": "updated"}, context=None
                )

        # Assert the uploaded document carries correct metadata (non-vacuous)
        upload_call = client.documents.upload.call_args
        uploaded_doc = upload_call.kwargs["documents"][0]
        assert uploaded_doc["id"] == "mem-008"
        assert "updated_at" in uploaded_doc, "updated_at timestamp is missing"
        assert "created_at" in uploaded_doc, "created_at timestamp is missing"
        assert uploaded_doc["agent_id"] == "test-agent"
        assert uploaded_doc["status"] == "active"


class TestConsistencyWithStoreMemory:
    """update_memory should mirror store_memory's validated construction pattern."""

    def test_same_validation_flow_as_store_memory(self):
        """Both update_memory and store_memory should follow: validate → build doc → upload."""
        update_flow = []
        store_flow = []

        # test update_memory flow
        client = make_client()
        service = MemoryWriteService(client)

        def track_update_val(memory, context=None):
            update_flow.append("validate")
            return {"action": "store", "reason": "ok"}

        with patch.object(MemoryReadService, "get_memory",
                          return_value=existing_doc()):
            with patch.object(service.validation_service, "validate_memory",
                              side_effect=track_update_val):
                def track_update_upload(*args, **kwargs):
                    update_flow.append("upload")
                    return {"status": "success"}
                with patch.object(client.documents, "upload",
                                  side_effect=track_update_upload):
                    service.update_memory(
                        "mem-009", "memanto_agent_test-agent",
                        {"content": "test"}, context=None
                    )

        # test store_memory flow
        client2 = make_client()
        service2 = MemoryWriteService(client2)

        def track_store_val(memory, context=None):
            store_flow.append("validate")
            return {"action": "store", "reason": "ok"}

        with patch.object(service2.validation_service, "validate_memory",
                          side_effect=track_store_val):
            def track_store_upload(*args, **kwargs):
                store_flow.append("upload")
                return {"status": "success"}
            with patch.object(client2.documents, "upload",
                              side_effect=track_store_upload):
                mem = make_memory(memory_id="mem-store", content="test store")
                service2.store_memory(mem)

        # Both must follow the same pattern: validate → upload
        assert update_flow == ["validate", "upload"]
        assert store_flow == ["validate", "upload"]
        assert update_flow == store_flow


class TestBatchConsistency:
    """update_memory's new behavior must not break batch_store_memories."""

    def test_batch_still_uses_validation(self):
        """batch_store_memories should continue to validate each memory."""
        client = make_client()
        service = MemoryWriteService(client)

        # Use different titles so both memories pass through validation
        # (same-type/same-title diff-content is handled by batch contradiction
        # resolution, which skips validate_memory for superseded entries)
        mem1 = make_memory(memory_id="mem-010", content="first", title="Topic A")
        mem2 = make_memory(memory_id="mem-011", content="second", title="Topic B")

        with patch.object(service.validation_service, "validate_memory",
                          return_value={"action": "store", "reason": "ok"}) as mock_val:
            service.batch_store_memories([mem1, mem2])

        # Each memory passes through validation
        assert mock_val.call_count == 2


class TestEdgeCases:
    """Edge cases that should not break."""

    def test_update_memory_with_existing_memory(self):
        """update_memory should handle existing memory retrieval gracefully."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc("mem-012")):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "updated memory"}
            ):
                result = service.update_memory(
                    "mem-012", "memanto_agent_test-agent",
                    {"content": "updated"}, context=None
                )

        assert result["action"] == "store"
        assert result["id"] == "mem-012"
        assert "updated_fields" in result

    def test_update_memory_preserves_memory_id(self):
        """The memory ID should be preserved through the pipeline."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory",
                          return_value=existing_doc("mem-preserve-me")):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ):
                service.update_memory(
                    "mem-preserve-me", "memanto_agent_test-agent",
                    {"content": "preserved"}, context=None
                )

        # The uploaded document must keep the memory ID
        upload_call = client.documents.upload.call_args
        uploaded_doc = upload_call.kwargs["documents"][0]
        assert uploaded_doc["id"] == "mem-preserve-me"

    def test_validation_result_without_memory_key(self):
        """When validation doesn't return a 'memory' key, original should be used."""
        client = make_client()
        service = MemoryWriteService(client)

        original_content = "unchanged content"

        with patch.object(MemoryReadService, "get_memory",
                          return_value=existing_doc("mem-013", content="old content")):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ):
                service.update_memory(
                    "mem-013", "memanto_agent_test-agent",
                    {"content": original_content}, context=None
                )

        # The uploaded document should use the original (non-modified) memory content
        upload_call = client.documents.upload.call_args
        uploaded_doc = upload_call.kwargs["documents"][0]
        assert original_content in uploaded_doc["text"]

    def test_update_memory_with_context(self):
        """update_memory should pass context through to validation."""
        client = make_client()
        service = MemoryWriteService(client)
        ctx = {"agent_id": "test-agent", "session_id": "sess-1"}

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ) as mock_val:
                service.update_memory(
                    "mem-014", "memanto_agent_test-agent",
                    {"content": "test"}, context=ctx
                )

        # Context must be forwarded to validate_memory
        call_kwargs = mock_val.call_args
        assert call_kwargs[0][1] == ctx  # second positional arg is context

    def test_update_memory_updated_fields_in_response(self):
        """The response must include the list of updated field names."""
        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ):
                result = service.update_memory(
                    "mem-015", "memanto_agent_test-agent",
                    {"content": "new", "confidence": 0.9}, context=None
                )

        assert "updated_fields" in result
        assert set(result["updated_fields"]) == {"content", "confidence"}

    def test_update_memory_response_has_status(self):
        """The response must include upload status from the Moorcheh client."""
        client = make_client(upload_result={"status": "success"})
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={"action": "store", "reason": "ok"}
            ):
                result = service.update_memory(
                    "mem-016", "memanto_agent_test-agent",
                    {"content": "test"}, context=None
                )

        assert result["status"] == "success"

    def test_contradiction_resolution_preserves_reason(self):
        """The reason from validation should be preserved in the response."""
        client = make_client()
        service = MemoryWriteService(client)

        reason = "contradiction resolved: superseded old-1; failed to supersede old-2"

        with patch.object(MemoryReadService, "get_memory", return_value=existing_doc()):
            with patch.object(
                service.validation_service, "validate_memory",
                return_value={
                    "action": "store",
                    "reason": reason,
                    "superseded_ids": ["old-1"],
                }
            ):
                result = service.update_memory(
                    "mem-017", "memanto_agent_test-agent",
                    {"content": "overriding content"}, context=None
                )

        assert result["reason"] == reason
        assert result["superseded_ids"] == ["old-1"]

    def test_missing_memory_raises_error(self):
        """update_memory should raise when memory is not found."""
        from memanto.app.utils.errors import MemoryError

        client = make_client()
        service = MemoryWriteService(client)

        with patch.object(MemoryReadService, "get_memory", return_value=None):
            with pytest.raises(MemoryError, match="not found"):
                service.update_memory(
                    "nonexistent", "memanto_agent_test-agent",
                    {"content": "test"}, context=None
                )
