from unittest.mock import MagicMock

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_validation_service import MemoryValidationService
from memanto.app.services.memory_write_service import MemoryWriteService


def make_memory(**overrides):
    defaults = {
        "content": "The user's favorite color is red.",
        "type": "fact",
        "title": "Favorite Color",
        "agent_id": "test-agent",
        "actor_id": "user",
        "source": "user",
    }
    defaults.update(overrides)
    return MemoryRecord(**defaults)


def make_client(search_results=None):
    client = MagicMock()
    client.documents.upload.return_value = {"status": "success"}
    client.documents.delete.return_value = {"actual_deletions": 1}
    client.similarity_search.query.return_value = {"results": search_results or []}
    return client


def existing_doc(
    memory_id="old-1",
    title="Favorite Color",
    content="The user's favorite color is blue.",
    memory_type="fact",
    status="active",
):
    """A stored memory as Moorcheh returns it (flat metadata fields)."""
    return {
        "id": memory_id,
        "text": f"[{memory_type.upper()}] {title}\n\n{content}",
        "memory_type": memory_type,
        "status": status,
        "agent_id": "test-agent",
        "actor_id": "user",
        "source": "user",
        "confidence": 0.8,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


class TestContradictionHandling:
    """Write-time contradiction validation in MemoryWriteService."""

    def test_store_memory_runs_validation(self):
        """store_memory must not blindly bypass validation (old 'MVP direct store')."""
        write_service = MemoryWriteService(make_client())

        result = write_service.store_memory(make_memory())

        assert result.get("reason") != "MVP direct store", (
            "Contradiction validation is completely skipped (MVP direct store)."
        )
        assert result["reason"] == "validated: no contradicting memories found"
        assert result["action"] == "store"

    def test_find_contradictions_matches_same_title_beyond_default_page(self):
        """Same-title contradictions outside the default top-10 page must still match."""
        filler = [
            existing_doc(
                memory_id=f"filler-{i}",
                title=f"Other topic {i}",
                content=f"Unrelated body {i}",
            )
            for i in range(12)
        ]
        contradicting = existing_doc(
            memory_id="old-1",
            title="Favorite Color",
            content="The user's favorite color is blue.",
        )
        client = make_client(search_results=filler + [contradicting])
        service = MemoryValidationService(client)

        conflicts = service._find_contradictions(make_memory())

        assert [item["id"] for item in conflicts] == ["old-1"]

    def test_prefetch_contradictions_runs_parallel_lookups(self, monkeypatch):
        """Batch prefetch should not serialize independent contradiction searches."""
        import time

        active = []

        def slow_find(_self, memory):
            active.append(memory.id)
            time.sleep(0.05)
            assert len(active) <= 8
            active.remove(memory.id)
            return []

        monkeypatch.setattr(
            MemoryValidationService,
            "_find_contradictions",
            slow_find,
        )
        service = MemoryValidationService(make_client())
        memories = [
            make_memory(title=f"Topic {i}", content=f"Body {i}") for i in range(4)
        ]

        start = time.perf_counter()
        prefetched = service.prefetch_contradictions(memories)
        elapsed = time.perf_counter() - start

        assert len(prefetched) == 4
        assert elapsed < 0.15

    def test_store_memory_supersedes_contradicting_memory(self):
        """A same-type/same-title active memory with different content is
        superseded (keep_new) and the resolution is reported."""
        client = make_client(search_results=[existing_doc()])
        write_service = MemoryWriteService(client)

        memory = make_memory()
        result = write_service.store_memory(memory)

        assert result["superseded_ids"] == ["old-1"]
        assert "contradiction resolved: superseded old-1" in result["reason"]

        # Old memory was rewritten as superseded history, not dropped.
        client.documents.delete.assert_not_called()
        uploads = client.documents.upload.call_args_list
        assert len(uploads) == 2
        superseded_doc = uploads[0].kwargs["documents"][0]
        assert superseded_doc["id"] == "old-1"
        assert superseded_doc["status"] == "superseded"
        assert superseded_doc["superseded_by"] == memory.id
        assert "superseded_at" in superseded_doc
        new_doc = uploads[1].kwargs["documents"][0]
        assert new_doc["id"] == memory.id
        assert new_doc["status"] == "active"

    def test_duplicate_content_is_not_a_contradiction(self):
        """Identical content under the same title is a duplicate, not a conflict."""
        duplicate = existing_doc(content="The user's favorite color is red.")
        client = make_client(search_results=[duplicate])
        write_service = MemoryWriteService(client)

        result = write_service.store_memory(make_memory())

        assert result["reason"] == "validated: no contradicting memories found"
        client.documents.delete.assert_not_called()

    def test_supersede_returns_false_when_upload_fails(self):
        """Failed supersede upload must not delete the original document."""
        client = make_client(search_results=[existing_doc()])
        client.documents.upload.side_effect = [
            {"status": "failed"},
            {"status": "success"},
        ]
        write_service = MemoryWriteService(client)

        result = write_service.store_memory(make_memory())

        assert result.get("superseded_ids", []) == []
        assert "failed to supersede old-1" in result["reason"]
        client.documents.delete.assert_not_called()

    def test_exempt_type_skips_conflict_check(self):
        """Types outside REQUIRE_VALIDATION_FOR store directly, without search."""
        client = make_client()
        write_service = MemoryWriteService(client)

        result = write_service.store_memory(
            make_memory(type="event", title="Standup", content="Daily standup at 9am.")
        )

        assert "exempt from conflict validation" in result["reason"]
        client.similarity_search.query.assert_not_called()

    def test_search_failure_does_not_block_store(self):
        """A failed conflict lookup is reported honestly but never blocks the write."""
        client = make_client()
        client.similarity_search.query.side_effect = RuntimeError("search down")
        write_service = MemoryWriteService(client)

        result = write_service.store_memory(make_memory())

        assert result["reason"] == "stored: conflict check unavailable"
        client.documents.upload.assert_called_once()

    def test_batch_store_memories_runs_validation(self):
        """batch_store_memories must not bypass validation either."""
        client = make_client()
        write_service = MemoryWriteService(client)

        memory1 = make_memory(content="The user lives in New York.", title="Location")
        memory2 = make_memory(content="The user lives in London.", title="Location")

        result = write_service.batch_store_memories([memory1, memory2])

        for res in result["results"]:
            assert res.get("reason") != "MVP direct store", (
                "Contradiction validation is skipped for batch storage (MVP direct store)."
            )

    def test_batch_resolves_contradictions_within_batch(self):
        """Contradicting memories submitted together resolve to last-wins,
        with the earlier one preserved as superseded history."""
        client = make_client()
        write_service = MemoryWriteService(client)

        memory1 = make_memory(content="The user lives in New York.", title="Location")
        memory2 = make_memory(content="The user lives in London.", title="Location")

        result = write_service.batch_store_memories([memory1, memory2])

        first, second = result["results"]
        assert first["action"] == "store_superseded"
        assert f"superseded within batch by {memory2.id}" in first["reason"]
        assert second["action"] == "store"

        documents = client.documents.upload.call_args.kwargs["documents"]
        assert documents[0]["status"] == "superseded"
        assert documents[0]["superseded_by"] == memory2.id
        assert documents[1]["status"] == "active"
        assert result["successful"] == 2
