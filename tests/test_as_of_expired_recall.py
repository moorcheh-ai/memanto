from memanto.app.services.memory_read_service import MemoryReadService


def _memory(memory_id: str, created_at: str, expires_at: str | None = None) -> dict:
    memory = {
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
    if expires_at:
        memory["expires_at"] = expires_at
    return memory


class _FakeDocuments:
    def __init__(self, items):
        self._items = items

    def fetch_text_data(self, **kwargs):
        return {
            "items": self._items,
            "pagination": {"has_more": False},
        }


class _FakeClient:
    def __init__(self, items):
        self.documents = _FakeDocuments(items)


def test_search_as_of_recalls_since_expired_memory():
    """A memory that was live at as_of_date but expired afterward must be recalled."""
    items = [
        _memory("temporal-fact", "2026-01-10T00:00:00Z", expires_at="2026-06-01T00:00:00Z"),
    ]
    service = MemoryReadService(_FakeClient(items))

    result = service.search_as_of(
        as_of_date="2026-01-15",
        agent_id="agent-1",
        limit=None,
    )

    ids = [memory["id"] for memory in result["results"]]
    assert "temporal-fact" in ids, "timeline amnesia: since-expired memory lost"


def test_search_as_of_excludes_memory_expired_before_as_of_date():
    """A memory that expired before as_of_date must NOT be recalled."""
    items = [
        _memory("expired-before", "2025-12-01T00:00:00Z", expires_at="2025-12-15T00:00:00Z"),
    ]
    service = MemoryReadService(_FakeClient(items))

    result = service.search_as_of(
        as_of_date="2026-01-15",
        agent_id="agent-1",
        limit=None,
    )

    ids = [memory["id"] for memory in result["results"]]
    assert "expired-before" not in ids


def test_search_as_of_recalls_non_expired_memory():
    """A memory that never expires must always be recalled."""
    items = [
        _memory("permanent", "2026-01-10T00:00:00Z"),
    ]
    service = MemoryReadService(_FakeClient(items))

    result = service.search_as_of(
        as_of_date="2026-01-15",
        agent_id="agent-1",
        limit=None,
    )

    ids = [memory["id"] for memory in result["results"]]
    assert "permanent" in ids
