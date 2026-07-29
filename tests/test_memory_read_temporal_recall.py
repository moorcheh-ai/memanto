"""
Regression tests for temporal / post-retrieval recall.

Covers the "timeline amnesia" bug where date-scoped (and other
post-retrieval) filters were applied only to the top ``limit + offset``
rows, silently dropping in-window memories that ranked just outside the
requested page.
"""

from memanto.app.services.memory_read_service import (
    MOORCHEH_MAX_TOP_K,
    MemoryReadService,
)


def _mem(mem_id: str, created_at: str) -> dict:
    return {
        "id": mem_id,
        "text": f"[FACT] Apollo note {mem_id}\n\nProject Apollo status",
        "memory_type": "fact",
        "scope_type": "agent",
        "scope_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
    }


class _RankedSimilaritySearch:
    """Fake backend that honours ``top_k`` like the real vector store."""

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


def _make_service():
    # 20 recent (June) rows rank ABOVE 5 older (January) rows by similarity.
    recent = [_mem(f"jun{i}", "2026-06-20T00:00:00Z") for i in range(20)]
    january = [_mem(f"jan{i}", "2026-01-10T00:00:00Z") for i in range(5)]
    return MemoryReadService(_Client(recent + january)), january


def test_temporal_window_recalls_rows_outside_the_top_page():
    """A January-scoped query must recall the January rows even though 20
    more-similar June rows precede them in the ranking."""
    service, january = _make_service()

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        created_after="2026-01-01T00:00:00Z",
        created_before="2026-01-31T23:59:59Z",
        limit=10,
    )

    returned = {m["id"] for m in result["results"]}
    assert returned == {m["id"] for m in january}


def test_post_retrieval_filter_widens_candidate_pool():
    """When a temporal filter is active the backend must be asked for a wide
    candidate pool, not just ``limit + offset`` rows."""
    service, _ = _make_service()

    service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        created_after="2026-01-01T00:00:00Z",
        limit=5,
    )

    assert service.client.similarity_search.last_kwargs["top_k"] == MOORCHEH_MAX_TOP_K


def test_unfiltered_query_still_widens_candidate_pool():
    """TTL enforcement (_filter_expired_memories) always runs as
    post-processing regardless of caller-supplied filters, so even a plain
    query without an explicit temporal/confidence filter must still widen the
    candidate pool - otherwise expired top-ranked rows could crowd out valid
    lower-ranked memories the same way an unfiltered temporal window would."""
    service, _ = _make_service()

    service.search_memories(query="Apollo", agent_id="agent-1", limit=5)

    assert service.client.similarity_search.last_kwargs["top_k"] == MOORCHEH_MAX_TOP_K
