"""
Test: update_memory preserves expires_at when ttl_seconds is absent.

Bug: When a memory has expires_at set but no ttl_seconds, any field
update silently drops the expiration, making the memory permanent.
Refs #770
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _make_existing_memory(expires_at_str="2026-12-31T23:59:59+00:00", ttl_seconds=None):
    """Build the dict that MemoryReadService.get_memory returns."""
    data = {
        "id": "mem_abc123",
        "title": "Test Memory",
        "content": "Some content",
        "type": "fact",
        "confidence": 0.9,
        "status": "active",
        "tags": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "agent_id": "agent1",
        "actor_id": "agent1",
        "source": "system",
        "provenance": "explicit_statement",
    }
    if expires_at_str:
        data["expires_at"] = expires_at_str
    if ttl_seconds is not None:
        data["ttl_seconds"] = ttl_seconds
    return data


@patch("memanto.app.services.memory_write_service.MemoryReadService")
def test_update_preserves_expires_at_without_ttl_seconds(MockReadService):
    """Updating a memory with expires_at but no ttl_seconds must keep expires_at."""
    from memanto.app.services.memory_write_service import MemoryWriteService

    client = MagicMock()
    # Simulate successful upload
    client.documents.upload.return_value = {"status": "success"}

    # Mock get_memory to return a memory with expires_at but no ttl_seconds
    mock_read = MockReadService.return_value
    mock_read.get_memory.return_value = _make_existing_memory(
        expires_at_str="2026-12-31T23:59:59+00:00",
        ttl_seconds=None,
    )

    service = MemoryWriteService(client)
    result = service.update_memory(
        memory_id="mem_abc123",
        namespace="memanto_agent_agent1",
        updates={"title": "Updated Title"},
    )

    # Verify the uploaded document contains expires_at
    upload_call = client.documents.upload.call_args
    uploaded_docs = upload_call[1].get("documents") or upload_call[0][1]
    doc = uploaded_docs[0] if isinstance(uploaded_docs, list) else uploaded_docs

    # The document metadata must include expires_at
    meta = doc.get("metadata", doc)
    assert meta.get("expires_at") is not None, (
        "expires_at was silently dropped during update! "
        "Memory with expires_at but no ttl_seconds lost its expiration."
    )


@patch("memanto.app.services.memory_write_service.MemoryReadService")
def test_update_preserves_expires_at_with_ttl_seconds(MockReadService):
    """Updating a memory with both expires_at and ttl_seconds must keep both."""
    from memanto.app.services.memory_write_service import MemoryWriteService

    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}

    mock_read = MockReadService.return_value
    mock_read.get_memory.return_value = _make_existing_memory(
        expires_at_str="2026-12-31T23:59:59+00:00",
        ttl_seconds=86400,
    )

    service = MemoryWriteService(client)
    result = service.update_memory(
        memory_id="mem_abc123",
        namespace="memanto_agent_agent1",
        updates={"title": "Updated Title"},
    )

    upload_call = client.documents.upload.call_args
    uploaded_docs = upload_call[1].get("documents") or upload_call[0][1]
    doc = uploaded_docs[0] if isinstance(uploaded_docs, list) else uploaded_docs

    meta = doc.get("metadata", doc)
    assert meta.get("expires_at") is not None
    assert meta.get("ttl_seconds") == 86400


@patch("memanto.app.services.memory_write_service.MemoryReadService")
def test_update_with_new_ttl_seconds_overrides_expires_at(MockReadService):
    """Setting ttl_seconds in updates should recalculate expires_at."""
    from memanto.app.services.memory_write_service import MemoryWriteService

    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}

    mock_read = MockReadService.return_value
    mock_read.get_memory.return_value = _make_existing_memory(
        expires_at_str="2026-12-31T23:59:59+00:00",
        ttl_seconds=86400,
    )

    service = MemoryWriteService(client)
    result = service.update_memory(
        memory_id="mem_abc123",
        namespace="memanto_agent_agent1",
        updates={"ttl_seconds": 3600},
    )

    upload_call = client.documents.upload.call_args
    uploaded_docs = upload_call[1].get("documents") or upload_call[0][1]
    doc = uploaded_docs[0] if isinstance(uploaded_docs, list) else uploaded_docs

    meta = doc.get("metadata", doc)
    # expires_at should be recalculated from the new ttl_seconds
    assert meta.get("ttl_seconds") == 3600
    assert meta.get("expires_at") is not None
