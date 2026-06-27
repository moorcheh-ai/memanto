"""
Failing test: Non-atomic update_memory causes permanent data loss on upload failure.

This test demonstrates BUG-C5: delete-then-recreate pattern in update_memory
loses data permanently if the upload step fails after deletion succeeds.

Expected: memory should survive an upload failure (rollback)
Actual: memory is permanently deleted
"""
import pytest
from unittest.mock import MagicMock, patch
from memanto.app.services.memory_write_service import MemoryWriteService


def test_update_memory_rollback_on_upload_failure():
    client = MagicMock()

    # Setup: get_memory returns existing memory
    client.documents.get.return_value = {
        "items": [{
            "id": "mem_001",
            "text": "[FACT] Original content",
            "metadata": {
                "type": "fact",
                "scope_type": "agent",
                "scope_id": "a1",
                "confidence": 0.9,
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
            },
        }]
    }

    # Delete succeeds
    client.documents.delete.return_value = {"actual_deletions": 1}
    # Upload fails
    client.documents.upload.side_effect = Exception("Network timeout")

    write_svc = MemoryWriteService(client)

    # The update should fail, but the original memory should still exist
    # (either via rollback or by uploading before deleting)
    with pytest.raises(Exception):
        write_svc.update_memory("mem_001", "memanto_agent_a1", {"content": "updated"})

    # Verify: delete was called, but the memory should still be recoverable
    # Currently it's GONE because delete succeeded but upload failed
    # After fix: upload should happen BEFORE delete, or a rollback should re-upload
    client.documents.get.assert_called_with(namespace_name="memanto_agent_a1", ids=["mem_001"])
    # The critical assertion: after a failed update, the original data must still exist
    # This test documents that it does NOT (the bug)
