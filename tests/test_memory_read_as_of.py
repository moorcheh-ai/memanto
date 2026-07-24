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
