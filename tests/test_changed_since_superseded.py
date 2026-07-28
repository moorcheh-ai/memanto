from memanto.app.services.memory_read_service import MemoryReadService


def _memory(memory_id: str, created_at: str, updated_at: str = None, status: str = "active") -> dict:
    return {
        "id": memory_id,
        "text": f"[FACT] {memory_id}\n\nStored memory",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
    }


class _FakeDocuments:
    def fetch_text_data(self, **kwargs):
        return {
            "items": [
                _memory("old-fact", "2026-01-10T09:00:00Z", updated_at="2026-01-18T12:00:00Z", status="superseded"),
                _memory("replacement", "2026-01-18T12:00:00Z"),
                _memory("unchanged", "2026-01-05T08:00:00Z"),
                _memory("late-update", "2026-01-08T10:00:00Z", updated_at="2026-01-19T14:00:00Z"),
            ],
            "pagination": {"has_more": False},
        }


class _FakeClient:
    documents = _FakeDocuments()


def test_changed_since_excludes_superseded_memories():
    """A superseded memory whose updated_at was bumped must NOT appear as a change."""
    service = MemoryReadService(_FakeClient())

    result = service.search_changed_since(
        since_date="2026-01-15T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "old-fact" not in ids
    assert "replacement" in ids

    by_id = {m["id"]: m for m in result["results"]}
    assert by_id["replacement"]["change_type"] == "created"
    assert by_id["late-update"]["change_type"] == "updated"


def test_changed_since_includes_genuinely_updated():
    """Active memories updated after since_date still appear normally."""
    service = MemoryReadService(_FakeClient())

    result = service.search_changed_since(
        since_date="2026-01-17T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "replacement" in ids
    assert "unchanged" not in ids

    by_id = {m["id"]: m for m in result["results"]}
    assert by_id["replacement"]["change_type"] == "created"
    assert by_id["late-update"]["change_type"] == "updated"


def test_changed_since_omitted_status_defaults_to_active():
    """A memory with no explicit status is treated as active and included."""
    class _NoStatusDocs:
        def fetch_text_data(self, **kwargs):
            mem = _memory("no-status", "2026-01-20T10:00:00Z")
            del mem["status"]
            return {"items": [mem], "pagination": {"has_more": False}}

    class _NoStatusClient:
        documents = _NoStatusDocs()

    service = MemoryReadService(_NoStatusClient())

    result = service.search_changed_since(
        since_date="2026-01-15T00:00:00Z",
        agent_id="agent-1",
        limit=None,
    )

    ids = [m["id"] for m in result["results"]]
    assert "no-status" in ids
    assert result["results"][0]["change_type"] == "created"
