"""
Regression tests for the conflict-resolution / contradiction-handling fix
and the update_memory data-loss fix (GitHub issue #1418).

All use a mocked Moorcheh client - no live backend needed.
"""

from unittest.mock import MagicMock

import pytest

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import MemoryError


def _mem(content, mtype="preference", confidence=0.9):
    return MemoryRecord(
        type=mtype,
        title="t",
        content=content,
        agent_id="agent-1",
        actor_id="user-1",
        source="user",
        confidence=confidence,
    )


class TestConflictResolution:
    def test_conflicting_memory_supersedes_previous_active_one(self):
        client = MagicMock()
        client.documents.upload.return_value = {"status": "success"}
        client.documents.delete.return_value = {
            "status": "success",
            "deleted_ids": ["old-1"],
        }

        # When the second memory is stored, the similarity search that backs
        # conflict detection returns the first as a high-similarity, same-type
        # active neighbour. Returning it twice also means the validation
        # repetition-check sees corroboration, so the new memory is stored as
        # a full (non-provisional) memory and is allowed to supersede.
        client.similarity_search.query.return_value = {
            "results": [
                {
                    "id": "old-1",
                    "score": 0.95,
                    "metadata": {"memory_type": "preference", "status": "active"},
                },
                {
                    "id": "old-2",
                    "score": 0.9,
                    "metadata": {"memory_type": "preference", "status": "active"},
                },
            ]
        }

        svc = MemoryWriteService(client)
        # get_memory is used by update_memory (invoked during supersede)
        from memanto.app.services import memory_read_service

        memory_read_service.MemoryReadService.get_memory = lambda self, mid, ns: {
            "id": mid,
            "type": "preference",
            "title": "t",
            "content": "old",
            "scope_type": "agent",
            "scope_id": "agent-1",
            "actor_id": "user-1",
            "source": "user",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        }

        result = svc.store_memory(_mem("The user's favorite color is red."))

        assert "old-1" in result["superseded_ids"]

    def test_no_conflict_when_types_differ(self):
        client = MagicMock()
        client.documents.upload.return_value = {"status": "success"}
        client.similarity_search.query.return_value = {
            "results": [
                {
                    "id": "other",
                    "score": 0.99,
                    "metadata": {"memory_type": "fact", "status": "active"},
                }
            ]
        }

        svc = MemoryWriteService(client)
        result = svc.store_memory(_mem("A preference", mtype="preference"))

        # Different memory_type -> not treated as a conflict
        assert result["superseded_ids"] == []

    def test_low_similarity_is_not_a_conflict(self):
        client = MagicMock()
        client.documents.upload.return_value = {"status": "success"}
        client.similarity_search.query.return_value = {
            "results": [
                {
                    "id": "unrelated",
                    "score": 0.2,
                    "metadata": {"memory_type": "preference", "status": "active"},
                }
            ]
        }

        svc = MemoryWriteService(client)
        result = svc.store_memory(_mem("Totally unrelated preference"))

        assert result["superseded_ids"] == []


class TestUpdateMemoryNoDataLoss:
    def test_failed_promotion_does_not_lose_data(self):
        """If the final re-upload under the real id fails, the update must
        raise - but the content must survive under the staging id, and the
        error must say where."""
        client = MagicMock()
        client.similarity_search.query.return_value = {"results": []}
        client.documents.delete.return_value = {
            "status": "success",
            "deleted_ids": ["mem-1"],
        }

        # First upload (staging) succeeds; second upload (promotion) fails.
        client.documents.upload.side_effect = [
            {"status": "queued"},
            ConnectionError("Moorcheh upload timed out"),
        ]

        from memanto.app.services import memory_read_service

        memory_read_service.MemoryReadService.get_memory = lambda self, mid, ns: {
            "id": mid,
            "type": "fact",
            "title": "t",
            "content": "original",
            "scope_type": "agent",
            "scope_id": "agent-1",
            "actor_id": "user-1",
            "source": "user",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        }

        svc = MemoryWriteService(client)
        with pytest.raises(MemoryError) as exc:
            svc.update_memory(
                "mem-1", "memanto_agent_agent-1", {"content": "new content"}
            )

        # The staging id is surfaced so the data is recoverable, not silently gone
        assert "staging" in str(exc.value)

        # And critically: the staged copy was written BEFORE the old doc was
        # deleted, so at no point did both the original and the replacement
        # cease to exist.
        first_upload_docs = client.documents.upload.call_args_list[0].kwargs["documents"]
        assert first_upload_docs[0]["id"].startswith("mem-1__staging_")

    def test_successful_update_cleans_up_staging(self):
        client = MagicMock()
        client.similarity_search.query.return_value = {"results": []}
        client.documents.delete.return_value = {
            "status": "success",
            "deleted_ids": ["mem-1"],
        }
        client.documents.upload.return_value = {"status": "queued"}

        from memanto.app.services import memory_read_service

        memory_read_service.MemoryReadService.get_memory = lambda self, mid, ns: {
            "id": mid,
            "type": "fact",
            "title": "t",
            "content": "original",
            "scope_type": "agent",
            "scope_id": "agent-1",
            "actor_id": "user-1",
            "source": "user",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        }

        svc = MemoryWriteService(client)
        result = svc.update_memory(
            "mem-1", "memanto_agent_agent-1", {"content": "new content"}
        )

        assert result["action"] == "updated"
        # Staging doc gets cleaned up: a delete call targets a staging id
        deleted_ids = [
            c.kwargs.get("ids", [None])[0] for c in client.documents.delete.call_args_list
        ]
        assert any(str(i).startswith("mem-1__staging_") for i in deleted_ids)
