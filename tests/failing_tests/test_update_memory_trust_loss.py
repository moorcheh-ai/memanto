"""
Failing test: update_memory erases trust/provenance fields.

This test demonstrates BUG-C6: update_memory does not carry over
provenance, validation_count, contradiction_detected, validated_at,
superseded_by, and supersedes from the original memory.

Expected: trust fields preserved across updates
Actual: all trust fields reset to defaults
"""
import pytest
from unittest.mock import MagicMock
from memanto.app.services.memory_write_service import MemoryWriteService


def test_update_memory_preserves_trust_fields():
    client = MagicMock()

    # Existing memory with rich trust metadata
    client.documents.get.return_value = {
        "items": [{
            "id": "mem_001",
            "text": "[FACT] We use PostgreSQL",
            "metadata": {
                "type": "fact",
                "scope_type": "agent",
                "scope_id": "a1",
                "confidence": 0.95,
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "provenance": "validated",
                "validation_count": 5,
                "contradiction_detected": True,
                "validated_at": "2026-06-01T00:00:00Z",
                "superseded_by": "mem_009",
                "supersedes": "mem_003",
            },
        }]
    }

    client.documents.delete.return_value = {"actual_deletions": 1}
    client.documents.upload.return_value = {"status": "queued"}

    write_svc = MemoryWriteService(client)

    # Edit just the title
    result = write_svc.update_memory(
        "mem_001",
        "memanto_agent_a1",
        {"title": "Database Choice"},
    )

    # Check what was uploaded
    upload_call = client.documents.upload.call_args
    uploaded_doc = upload_call.kwargs["documents"][0]

    # Trust fields should be preserved from original
    meta = uploaded_doc["metadata"] if "metadata" in uploaded_doc else uploaded_doc

    assert meta.get("provenance") == "validated", \
        f"provenance should be 'validated', got '{meta.get('provenance')}'"
    assert meta.get("validation_count") == 5, \
        f"validation_count should be 5, got {meta.get('validation_count')}"
    assert meta.get("contradiction_detected") == True, \
        f"contradiction_detected should be True, got {meta.get('contradiction_detected')}"
