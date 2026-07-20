"""
Tests for issue #1335: update_memory() overwrites entire record including
original_id — data_store.json not properly updated (on-prem).

These tests verify that update_memory() preserves immutable fields
(original_id, created_at) and only updates mutable fields.
"""
from unittest.mock import MagicMock, patch

import pytest

from memanto.app.services.memory_write_service import MemoryWriteService


class TestUpdateMemoryPreservesProvenance:
    """Verify that update_memory() does not overwrite immutable fields."""

    @pytest.fixture
    def mock_client(self):
        """Moorcheh client mock."""
        return MagicMock()

    @pytest.fixture
    def write_service(self, mock_client):
        """MemoryWriteService with mocked client."""
        return MemoryWriteService(mock_client)

    @pytest.fixture
    def existing_memory_data(self):
        """Simulate the data returned by get_memory for an existing record.

        This mimics what the on-prem backend or cloud API returns when
        reading a memory that has original_id in its metadata.
        Tags stored as list (the Moorcheh document format stores them
        as a comma-separated string in metadata, but _format_memory_item
        normalizes them to a list before returning).
        """
        return {
            "id": "mem_abc123",
            "text": "[FACT] Original Title\n\nOriginal content",
            "title": "Original Title",
            "content": "Original content",
            "metadata": {
                "id": "mem_abc123",
                "original_id": "mem_abc123",
                "memory_type": "fact",
                "agent_id": "test-agent",
                "actor_id": "user",
                "source": "user",
                "confidence": 0.8,
                "status": "active",
                "provenance": "explicit_statement",
                "created_at": "2026-07-01T10:00:00+00:00",
                "updated_at": "2026-07-01T10:00:00+00:00",
                "tags": ["tag1", "tag2"],
            },
        }

    def test_update_preserves_original_id(self, write_service, mock_client, existing_memory_data):
        """update_memory() must preserve original_id from existing metadata.

        Regression test for issue #1335: original_id was being dropped
        during update because it's not a field on MemoryRecord.
        """
        mock_read_service = MagicMock()
        mock_read_service.get_memory.return_value = existing_memory_data
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService",
            return_value=mock_read_service,
        ):
            updates = {"content": "Updated content", "title": "Updated Title"}
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates=updates,
            )

            # Assert: the uploaded document must contain original_id
            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            assert "original_id" in doc, (
                f"original_id was dropped during update. "
                f"Document keys: {sorted(doc.keys())}"
            )
            assert doc["original_id"] == "mem_abc123", (
                f"original_id changed from 'mem_abc123' to '{doc['original_id']}'"
            )

    def test_update_preserves_created_at(self, write_service, mock_client, existing_memory_data):
        """update_memory() must preserve created_at from existing metadata."""
        mock_read_service = MagicMock()
        mock_read_service.get_memory.return_value = existing_memory_data
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService",
            return_value=mock_read_service,
        ):
            updates = {"content": "Updated content"}
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates=updates,
            )

            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            # created_at must be preserved, not overwritten with "now"
            assert doc["created_at"].startswith("2026-07-01"), (
                f"created_at was overwritten: expected 2026-07-01, got {doc['created_at']}"
            )

    def test_update_does_not_overwrite_original_id_with_new_id(self, write_service, mock_client):
        """When the caller passes a different memory_id on update,
        original_id must still point to the FIRST id, not the new one.

        This is the core bug reported in issue #1335:
        'On subsequent updates, original_id becomes equal to the latest memory_id'
        """
        existing_data = {
            "id": "mem_abc123",
            "text": "[FACT] Original\n\nOriginal content",
            "title": "Original",
            "content": "Original content",
            "metadata": {
                "id": "mem_abc123",
                "original_id": "mem_abc123",
                "memory_type": "fact",
                "agent_id": "test-agent",
                "actor_id": "user",
                "source": "user",
                "confidence": 0.8,
                "status": "active",
                "provenance": "explicit_statement",
                "created_at": "2026-07-01T10:00:00+00:00",
                "updated_at": "2026-07-01T10:00:00+00:00",
                "tags": [],
            },
        }

        mock_read_service = MagicMock()
        mock_read_service.get_memory.return_value = existing_data
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService",
            return_value=mock_read_service,
        ):
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates={"content": "Updated content"},
            )

            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            assert doc.get("original_id") == "mem_abc123", (
                f"original_id should be 'mem_abc123' but got '{doc.get('original_id')}'"
            )

    def test_update_only_touches_allowed_fields(self, write_service, mock_client, existing_memory_data):
        """update_memory() must only update fields in ALLOWED_UPDATE_FIELDS,
        leaving all other metadata untouched.
        """
        mock_read_service = MagicMock()
        mock_read_service.get_memory.return_value = existing_memory_data
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService",
            return_value=mock_read_service,
        ):
            updates = {"content": "New content", "tags": ["new_tag"]}
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates=updates,
            )

            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            # Immutable fields preserved
            assert doc.get("original_id") == "mem_abc123"
            assert doc.get("agent_id") == "test-agent"
            assert doc.get("provenance") == "explicit_statement"
            # created_at preserved, updated_at is recent
            assert doc["created_at"].startswith("2026-07-01")

    def test_update_preserves_provenance_type(self, write_service, mock_client):
        """update_memory() must preserve provenance when not in updates."""
        existing_data = {
            "id": "mem_abc123",
            "text": "[FACT] Test\n\nTest content",
            "title": "Test",
            "content": "Test content",
            "metadata": {
                "id": "mem_abc123",
                "original_id": "mem_abc123",
                "memory_type": "fact",
                "agent_id": "test-agent",
                "actor_id": "user",
                "source": "user",
                "confidence": 0.8,
                "status": "active",
                "provenance": "inferred",
                "created_at": "2026-07-01T10:00:00+00:00",
                "updated_at": "2026-07-01T10:00:00+00:00",
                "tags": [],
            },
        }

        mock_read_service = MagicMock()
        mock_read_service.get_memory.return_value = existing_data
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService",
            return_value=mock_read_service,
        ):
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates={"content": "Updated"},
            )

            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            assert doc.get("provenance") == "inferred", (
                f"provenance should be 'inferred' but got '{doc.get('provenance')}'"
            )


class TestOriginalIdPreservedThroughReadPath:
    """Verify that original_id survives the full read-format-update cycle.

    Issue #1335 reports that original_id is lost during update. The root cause
    is that _format_memory_item() strips extra metadata keys like original_id,
    so update_memory() never sees them even though the extra-metadata
    preservation code would otherwise preserve them.
    """

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def write_service(self, mock_client):
        return MemoryWriteService(mock_client)

    def test_original_id_survives_read_format_update_cycle(self, write_service, mock_client):
        """original_id from the raw Moorcheh document must survive the
        get_memory() -> _format_memory_item() -> update_memory() round trip.

        This test simulates the real flow: the Moorcheh SDK returns a document
        with original_id in metadata, _format_memory_item() processes it, then
        update_memory() reads it back and must preserve original_id.
        """
        from memanto.app.services.memory_read_service import MemoryReadService

        # Simulate the raw Moorcheh SDK response (what documents.get returns)
        raw_moorcheh_document = {
            "id": "mem_abc123",
            "text": "[FACT] Original Title\n\nOriginal content\n\nTags: tag1, tag2",
            "metadata": {
                "id": "mem_abc123",
                "original_id": "mem_abc123",
                "memory_type": "fact",
                "agent_id": "test-agent",
                "actor_id": "user",
                "source": "user",
                "confidence": 0.8,
                "status": "active",
                "provenance": "explicit_statement",
                "created_at": "2026-07-01T10:00:00+00:00",
                "updated_at": "2026-07-01T10:00:00+00:00",
                "tags": "tag1,tag2",
            },
        }

        # Process it through _format_memory_item (what get_memory returns)
        read_service = MemoryReadService(mock_client)
        formatted = read_service._format_memory_item(raw_moorcheh_document)

        # Verify: original_id must be present in the formatted output
        # If this assertion fails, _format_memory_item is stripping original_id
        assert "original_id" in formatted, (
            f"_format_memory_item strips original_id from the document. "
            f"Keys in formatted output: {sorted(formatted.keys())}. "
            f"Extra metadata keys from the Moorcheh document must be preserved "
            f"so that update_memory() can carry them through."
        )

        # Now verify that update_memory preserves original_id through the
        # full read-then-write cycle
        mock_client.documents.upload.return_value = {"status": "success"}

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=formatted,
        ):
            write_service.update_memory(
                memory_id="mem_abc123",
                namespace="memanto_agent_test-agent",
                updates={"content": "Updated content"},
            )

            upload_call = mock_client.documents.upload.call_args
            uploaded_documents = upload_call.kwargs.get("documents") or upload_call[1].get("documents")
            doc = uploaded_documents[0]

            assert doc.get("original_id") == "mem_abc123", (
                f"original_id lost in read-format-update cycle. "
                f"Got: {doc.get('original_id')}"
            )
