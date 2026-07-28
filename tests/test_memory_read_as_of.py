from memanto.app.services.memory_read_service import MemoryReadService


def _memory(memory_id: str, created_at: str) -> dict:
    return {
        "id": memory_id,
        "text": f"[FACT] {memory_id}\n\nStored memory",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
    }


class _FakeDocuments:
    def fetch_text_data(self, **kwargs):
        return {
            "items": [
                _memory("morning", "2026-01-15T09:00:00Z"),
                _memory("evening", "2026-01-15T18:00:00Z"),
                _memory("next-day", "2026-01-16T00:00:00Z"),
            ],
            "pagination": {"has_more": False},
        }


class _FakeClient:
    documents = _FakeDocuments()


def test_search_as_of_date_only_includes_the_whole_day():
    service = MemoryReadService(_FakeClient())

    result = service.search_as_of(
        as_of_date="2026-01-15",
        agent_id="agent-1",
        limit=None,
    )

    assert [memory["id"] for memory in result["results"]] == [
        "morning",
        "evening",
    ]


def test_search_as_of_full_timestamp_keeps_exact_cutoff():
    service = MemoryReadService(_FakeClient())

    result = service.search_as_of(
        as_of_date="2026-01-15T12:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    assert [memory["id"] for memory in result["results"]] == ["morning"]


def _superseded_memory(
    memory_id: str, created_at: str, superseded_at: str
) -> dict:
    return {
        "id": memory_id,
        "text": f"[FACT] {memory_id}\n\nOld contradicted fact",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "superseded",
        "created_at": created_at,
        "updated_at": superseded_at,
        "superseded_by": "replacement",
        "superseded_at": superseded_at,
    }


class _FakeDocumentsWithSuperseded:
    def fetch_text_data(self, **kwargs):
        return {
            "items": [
                _superseded_memory(
                    "old-fact", "2026-01-01T10:00:00Z", "2026-01-10T12:00:00Z"
                ),
                _memory("replacement", "2026-01-10T12:00:00Z"),
            ],
            "pagination": {"has_more": False},
        }


class _FakeClientWithSuperseded:
    documents = _FakeDocumentsWithSuperseded()


def test_search_as_of_excludes_superseded_before_cutoff():
    """A memory superseded on Jan 10 must NOT appear in a Jan 15 as_of query."""
    service = MemoryReadService(_FakeClientWithSuperseded())

    result = service.search_as_of(
        as_of_date="2026-01-15T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "old-fact" not in ids
    assert "replacement" in ids


def test_search_as_of_includes_superseded_after_cutoff():
    """A memory superseded on Jan 10 WAS still active on Jan 5 — include it."""
    service = MemoryReadService(_FakeClientWithSuperseded())

    result = service.search_as_of(
        as_of_date="2026-01-05T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "old-fact" in ids
    assert "replacement" not in ids


def _superseded_no_timestamp(memory_id: str, created_at: str) -> dict:
    return {
        "id": memory_id,
        "text": f"[FACT] {memory_id}\n\nOld fact",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "superseded",
        "created_at": created_at,
        "updated_at": None,
    }


class _FakeDocumentsNoTimestamp:
    def fetch_text_data(self, **kwargs):
        return {
            "items": [
                _superseded_no_timestamp("no-ts", "2026-01-01T10:00:00Z"),
            ],
            "pagination": {"has_more": False},
        }


class _FakeClientNoTimestamp:
    documents = _FakeDocumentsNoTimestamp()


def test_search_as_of_fail_open_missing_updated_at():
    """Superseded memory with no updated_at is included (fail-open)."""
    service = MemoryReadService(_FakeClientNoTimestamp())

    result = service.search_as_of(
        as_of_date="2026-01-15T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "no-ts" in ids
