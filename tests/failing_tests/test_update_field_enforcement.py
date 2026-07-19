"""
Regression test: update_memory must enforce ALLOWED_UPDATE_FIELDS

Reproduces the bug where caller-supplied fields outside ALLOWED_UPDATE_FIELDS
(such as status, actor_id, provenance) are passed through to the MemoryRecord
constructor, allowing privilege escalation through the update path.

Run: pytest tests/failing_tests/test_update_field_enforcement.py -v
"""
from unittest.mock import MagicMock, patch

import pytest

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService


@pytest.fixture
def mock_client():
    client = MagicMock()
    # Return an existing memory for the fetch step
    client.documents.list.return_value = {
        "documents": [{
            "id": "mem_test01",
            "text": "[FACT] Test memory",
            "memory_type": "fact",
            "agent_id": "agent-1",
            "actor_id": "user-1",
            "source": "user",
            "confidence": 0.9,
            "status": "active",
            "provenance": "explicit_statement",
            "created_at": "2026-07-01T00:00:00",
            "updated_at": "2026-07-01T00:00:00",
        }]
    }
    client.documents.upload.return_value = {"status": "success"}
    return client


@pytest.fixture
def svc(mock_client):
    return MemoryWriteService(mock_client)


class TestUpdateFieldEnforcement:
    """update_memory should strip fields not in ALLOWED_UPDATE_FIELDS."""

    def test_status_cannot_be_changed_via_update(self, svc, mock_client):
        """Setting status='deleted' through update_memory must be blocked."""
        svc.update_memory(
            memory_id="mem_test01",
            namespace="memanto_agent_agent-1",
            updates={"content": "Edited content", "status": "deleted"},
        )
        upload_call = mock_client.documents.upload.call_args
        doc = upload_call[1]["documents"][0] if upload_call[1] else upload_call[0][1][0]
        assert doc.get("status") != "deleted", (
            "status field was passed through despite not being in ALLOWED_UPDATE_FIELDS"
        )

    def test_actor_id_cannot_be_changed_via_update(self, svc, mock_client):
        """Changing actor_id through update_memory must be blocked."""
        svc.update_memory(
            memory_id="mem_test01",
            namespace="memanto_agent_agent-1",
            updates={"content": "Edited content", "actor_id": "attacker"},
        )
        upload_call = mock_client.documents.upload.call_args
        doc = upload_call[1]["documents"][0] if upload_call[1] else upload_call[0][1][0]
        assert doc.get("actor_id") != "attacker", (
            "actor_id was passed through despite not being in ALLOWED_UPDATE_FIELDS"
        )

    def test_provenance_cannot_be_changed_via_update(self, svc, mock_client):
        """Changing provenance through update_memory must be blocked."""
        svc.update_memory(
            memory_id="mem_test01",
            namespace="memanto_agent_agent-1",
            updates={"content": "Edited content", "provenance": "validated"},
        )
        upload_call = mock_client.documents.upload.call_args
        doc = upload_call[1]["documents"][0] if upload_call[1] else upload_call[0][1][0]
        assert doc.get("provenance") != "validated", (
            "provenance was passed through despite not being in ALLOWED_UPDATE_FIELDS"
        )

    def test_allowed_fields_still_work(self, svc, mock_client):
        """Fields in ALLOWED_UPDATE_FIELDS must still be applied."""
        svc.update_memory(
            memory_id="mem_test01",
            namespace="memanto_agent_agent-1",
            updates={"title": "New Title", "content": "New Content", "confidence": 0.5},
        )
        upload_call = mock_client.documents.upload.call_args
        doc = upload_call[1]["documents"][0] if upload_call[1] else upload_call[0][1][0]
        assert doc.get("title") == "New Title"
        assert "New Content" in doc.get("text", "")
