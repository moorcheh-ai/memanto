```python
"""
Regression tests for temporal / post-retrieval recall with tenant isolation.

Covers the "timeline amnesia" bug where date-scoped filters were applied only
to the top rows, silently dropping in-window memories that ranked just outside
the requested page. Also verifies tenant isolation is maintained.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService

def _mem(mem_id: str, created_at: str, scope_id: str) -> dict:
    return {
        "id": mem_id,
        "text": f"[FACT] Apollo note {mem_id}\n\nProject Apollo status",
        "memory_type": "fact",
        "scope_type": "agent",
        "scope_id": scope_id,
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
    }

class _RankedSimilaritySearch:
    """Fake backend that honours tenant isolation and top_k."""

    def __init__(self, ranked_rows):
        self._ranked_rows = ranked_rows
        self.last_kwargs = None

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        top_k = kwargs.get("top_k")
        rows = self._ranked_rows[:top_k] if top_k else self._ranked_rows
        return {"results": rows, "execution_time": 0}

class _Client:
    def __init__(self, ranked_rows):
        self.similarity_search = _RankedSimilaritySearch(ranked_rows)

def _make_service(tenant_id: str):
    # 20 recent (June) rows from tenant-1 rank ABOVE 5 older (January) rows from tenant-2
    recent = [_mem(f"jun{i}", "2026-06-20T00:00:00Z", tenant_id) for i in range(20)]
    cross_tenant = [_mem(f"jan{i}", "2026-01-10T00:00:00Z", f"tenant-{1 if tenant_id == 'tenant-0' else 0}")
                   for i in range(5)]
    return MemoryReadService(_Client(recent + cross_tenant), tenant_id), recent

def test_cross_tenant_isolation_with_temporal_query():
    """Tenant-0 query must NOT return tenant-1 memories even with temporal filter."""
    service, _ = _make_service("tenant-0")

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        created_after="2026-01-01T00:00:00Z",
        created_before="2026-01-31T23:59:59Z",
        limit=10,
    )

    returned = {m["id"] for m in result["results"]}
    assert returned == set()  # No cross-tenant memories returned

def test_temporal_window_recalls_rows_outside_the_top_page():
    """A January-scoped query must recall the January rows even though 20
    more-similar June rows precede them in the ranking."""
    service, january = _make_service("tenant-0")

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        created_after="2026-01-01T00:00:00Z",
        created_before="2026-01-31T23:59:59Z",
        limit=10,
    )

    returned = {m["id"] for m in result["results"]}
    assert returned == {m["id"] for m in january}

def test_invalid_temporal_filters_are_rejected():
    """Invalid date ranges must raise ValueError."""
    service, _ = _make_service("tenant-0")

    with pytest.raises(ValueError, match="created_after must be before created_before"):
        service.search_memories(
            query="Apollo",
            agent_id="agent-1",
            created_after="2026-02-01T00:00:00Z",
            created_before="2026-01-31T23:59:59Z",
            limit=5,
        )

def test_missing_scope_id_in_results_is_rejected():
    """Memories without scope_id must be filtered out."""
    service, _ = _make_service("tenant-0")

    # Mock client that returns memory without scope_id
    mock_client = MagicMock()
    mock_client.similarity_search.query.return_value = {
        "results": [_mem("bad", "2026-01-10T00:0