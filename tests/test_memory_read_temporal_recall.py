"""
Regression tests for temporal / post-retrieval recall.

Covers the "timeline amnesia" bug where date-scoped (and other
post-retrieval) filters were applied only to the top ``limit + offset``
rows, silently dropping in-window memories that ranked just outside the
requested page.
"""

import pytest

from memanto.app.services.memory_read_service import (
    MOORCHEH_MAX_TOP_K,
    MemoryReadService,
)
from memanto.app.utils.errors import MemoryOperationError


def _mem(
    mem_id: str,
    created_at: str = "2026-06-20T00:00:00Z",
    *,
    status: str | None = "active",
    include_status: bool = True,
    score: float = 0.9,
    memory_type: str = "fact",
    confidence: float | None = 0.9,
) -> dict:
    row: dict = {
        "id": mem_id,
        "text": f"[{memory_type.upper()}] Apollo note {mem_id}\n\nProject Apollo status",
        "memory_type": memory_type,
        "scope_type": "agent",
        "scope_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": confidence,
        "created_at": created_at,
        "updated_at": created_at,
        "score": score,
    }
    if include_status:
        row["status"] = status
    return row


class _RankedSimilaritySearch:
    """Fake backend that honours ``top_k`` like the real vector store."""

    def __init__(self, ranked_rows, per_call_rows=None, per_call_responses=None):
        self._ranked_rows = ranked_rows
        self._per_call_rows = per_call_rows
        self._per_call_responses = per_call_responses
        self.last_kwargs = None
        self.calls: list[dict] = []

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        self.calls.append(kwargs)
        call_index = len(self.calls) - 1
        if self._per_call_responses is not None:
            outcome = self._per_call_responses[call_index]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        top_k = kwargs.get("top_k")
        source_rows = (
            self._per_call_rows[call_index]
            if self._per_call_rows is not None
            else self._ranked_rows
        )
        rows = source_rows[:top_k] if top_k else source_rows
        return {"results": rows, "execution_time": 0}


class _Client:
    def __init__(self, ranked_rows, per_call_rows=None, per_call_responses=None):
        self.similarity_search = _RankedSimilaritySearch(
            ranked_rows,
            per_call_rows=per_call_rows,
            per_call_responses=per_call_responses,
        )


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


def test_unfiltered_query_does_not_widen_candidate_pool():
    """An unfiltered query should not over-fetch candidates, to avoid the
    p95 latency penalty on simple recall queries. Post-processing filters like TTL
    are only applied when explicitly requested."""
    service, _ = _make_service()

    service.search_memories(query="Apollo", agent_id="agent-1", limit=5)

    assert service.client.similarity_search.last_kwargs["top_k"] == 5


def test_active_search_defaults_to_full_pool_without_adaptive_flag():
    """Direct callers without _adaptive_fetch=True preserve top_k=100 behavior."""
    rows = [_mem(f"a{i}", score=1.0 - i * 0.01) for i in range(60)]
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo", agent_id="agent-1", status="active", limit=5
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        MOORCHEH_MAX_TOP_K
    ]
    assert result["total_available"] == 60
    assert result["has_more"] is True


@pytest.mark.parametrize("limit,expected_top_k", [(5, 25), (20, 40), (60, 100)])
def test_adaptive_active_search_uses_initial_pool_and_skips_retry_when_sufficient(
    limit: int, expected_top_k: int
):
    """Adaptive active-only searches start at min(max(limit*2, 25), 100) and avoid retry."""
    rows = [_mem(f"a{i}", score=1.0 - i * 0.005) for i in range(100)]
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="active",
        limit=limit,
        _adaptive_fetch=True,
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        expected_top_k
    ]
    assert [m["id"] for m in result["results"]] == [f"a{i}" for i in range(limit)]


def test_adaptive_active_search_retries_once_at_max_on_full_insufficient_batch():
    """Insufficient active rows in a full initial batch trigger one retry at 100."""
    first_25 = [_mem(f"early{i}", score=0.99 - i * 0.01) for i in range(3)] + [
        _mem(f"exp{i}", status="expired", score=0.90 - i * 0.01) for i in range(22)
    ]
    tail = [_mem(f"tail{i}", score=0.50 - i * 0.01) for i in range(10)]
    service = MemoryReadService(_Client(first_25 + tail))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        tags=["release"],
        status="active",
        limit=5,
        min_similarity_score=0.4,
        _adaptive_fetch=True,
    )

    calls = service.client.similarity_search.calls
    assert [c["top_k"] for c in calls] == [25, MOORCHEH_MAX_TOP_K]
    for key in ("query", "namespaces", "threshold", "kiosk_mode"):
        assert calls[0][key] == calls[1][key]
    assert [m["id"] for m in result["results"]] == [
        "early0",
        "early1",
        "early2",
        "tail0",
        "tail1",
    ]


def test_adaptive_retry_replaces_initial_batch_without_duplicates():
    """Retry replaces the first result set rather than appending to it."""
    batch1 = [_mem("shared-active", score=0.95)] + [
        _mem(f"exp{i}", status="expired", score=0.90 - i * 0.01) for i in range(24)
    ]
    batch2 = [
        _mem("shared-active", score=0.95),
        _mem("exp-ignored", status="expired", score=0.92),
        _mem("tail-1", score=0.88),
        _mem("tail-2", score=0.85),
    ]
    service = MemoryReadService(_Client([], per_call_rows=[batch1, batch2]))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="active",
        limit=3,
        _adaptive_fetch=True,
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        25,
        MOORCHEH_MAX_TOP_K,
    ]
    assert [m["id"] for m in result["results"]] == ["shared-active", "tail-1", "tail-2"]
    assert result["total_found"] == 3


def test_adaptive_active_search_does_not_retry_short_backend_response():
    """If the backend returned fewer than initial_top_k raw rows, do not retry."""
    short_rows = [_mem("only-active-1"), _mem("only-active-2")] + [
        _mem(f"exp{i}", status="expired") for i in range(10)
    ]
    service = MemoryReadService(_Client(short_rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="active",
        limit=5,
        _adaptive_fetch=True,
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [25]
    assert [m["id"] for m in result["results"]] == ["only-active-1", "only-active-2"]


def test_adaptive_active_search_counts_legacy_missing_status_as_active():
    """Records without a stored status remain active and avoid unnecessary retries."""
    rows = (
        [_mem(f"legacy-missing-{i}", include_status=False) for i in range(3)]
        + [_mem(f"legacy-none-{i}", status=None) for i in range(2)]
        + [_mem(f"exp{i}", status="expired") for i in range(25)]
    )
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="active",
        limit=5,
        _adaptive_fetch=True,
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [25]
    assert [m["id"] for m in result["results"]] == [
        "legacy-missing-0",
        "legacy-missing-1",
        "legacy-missing-2",
        "legacy-none-0",
        "legacy-none-1",
    ]
    assert all(m["status"] == "active" for m in result["results"])


@pytest.mark.parametrize(
    "extra_kwargs",
    [
        {"created_after": "2026-01-01T00:00:00Z"},
        {"created_before": "2026-12-31T23:59:59Z"},
        {"min_confidence": 0.8},
        {"offset": 2},
    ],
)
def test_adaptive_fetch_excluded_for_temporal_confidence_and_offset(
    extra_kwargs: dict,
):
    """Temporal, confidence, and offset > 0 queries retain top_k=100 single-call behavior."""
    rows = [_mem(f"a{i}", score=1.0 - i * 0.01) for i in range(40)]
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="active",
        limit=5,
        _adaptive_fetch=True,
        **extra_kwargs,
    )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        MOORCHEH_MAX_TOP_K
    ]
    if "offset" in extra_kwargs:
        assert result["total_available"] == 40
        assert result["has_more"] is True
        assert [m["id"] for m in result["results"]] == [f"a{i}" for i in range(2, 7)]


def test_adaptive_fetch_excluded_for_multi_type_search():
    """Multi-type searches keep top_k=100 per type and re-rank union by score."""
    rows = [
        _mem("fact-low", memory_type="fact", score=0.70),
        _mem("pref-high", memory_type="preference", score=0.95),
        _mem("fact-exp", memory_type="fact", status="expired", score=0.99),
    ]
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        type=["fact", "preference"],
        status="active",
        limit=5,
        _adaptive_fetch=True,
    )

    calls = service.client.similarity_search.calls
    assert [c["top_k"] for c in calls] == [MOORCHEH_MAX_TOP_K, MOORCHEH_MAX_TOP_K]
    assert [m["id"] for m in result["results"]] == ["pref-high", "fact-low"]


def test_expired_status_retains_full_pool_and_no_query_pushdown():
    """Expired-only searches keep top_k=100 without injecting #status:expired."""
    rows = [_mem("active-0")] + [_mem(f"exp-{i}", status="expired") for i in range(3)]
    service = MemoryReadService(_Client(rows))

    result = service.search_memories(
        query="Apollo",
        agent_id="agent-1",
        status="expired",
        limit=5,
        _adaptive_fetch=True,
    )

    calls = service.client.similarity_search.calls
    assert [c["top_k"] for c in calls] == [MOORCHEH_MAX_TOP_K]
    assert "#status:expired" not in calls[0]["query"]
    assert [m["id"] for m in result["results"]] == ["exp-0", "exp-1", "exp-2"]


def _expired_heavy_first_batch() -> dict:
    """Return 25 rows with only 2 active items so adaptive fetch triggers one retry."""
    rows = [_mem(f"early-{i}", score=0.95 - i * 0.01) for i in range(2)] + [
        _mem(f"exp-{i}", status="expired", score=0.90 - i * 0.01) for i in range(23)
    ]
    return {"results": rows, "execution_time": 0}


def test_adaptive_retry_exception_raises_memory_operation_error_without_partial_fallback():
    """Exceptions raised by the retry call propagate via MemoryOperationError, not batch 1."""
    service = MemoryReadService(
        _Client(
            [],
            per_call_responses=[
                _expired_heavy_first_batch(),
                RuntimeError("Moorcheh backend timeout"),
            ],
        )
    )

    with pytest.raises(
        MemoryOperationError,
        match="Failed to search memories: Moorcheh backend timeout",
    ):
        service.search_memories(
            query="Apollo",
            agent_id="agent-1",
            status="active",
            limit=5,
            _adaptive_fetch=True,
        )

    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        25,
        MOORCHEH_MAX_TOP_K,
    ]


def test_adaptive_retry_preserves_memory_operation_error_without_rewrapping():
    """A MemoryOperationError from the retry call re-raises untouched without batch 1 fallback."""
    service = MemoryReadService(
        _Client(
            [],
            per_call_responses=[
                _expired_heavy_first_batch(),
                MemoryOperationError(
                    "Upstream search quota exceeded", details={"code": 429}
                ),
            ],
        )
    )

    with pytest.raises(MemoryOperationError) as exc_info:
        service.search_memories(
            query="Apollo",
            agent_id="agent-1",
            status="active",
            limit=5,
            _adaptive_fetch=True,
        )

    assert exc_info.value.message == "Upstream search quota exceeded"
    assert exc_info.value.details == {"code": 429}
    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        25,
        MOORCHEH_MAX_TOP_K,
    ]


@pytest.mark.parametrize(
    ("malformed_response", "expected_message", "expected_detail_key"),
    [
        (
            "not-a-dict",
            "Data corruption detected: Received malformed search result from storage layer.",
            "result_preview",
        ),
        (
            {"error": "backend unavailable"},
            "Data corruption detected: Missing 'results' key in search result from storage layer.",
            "result_preview",
        ),
        (
            {"results": "not-a-list"},
            "Data corruption detected: Received malformed search result array from storage layer.",
            "items_preview",
        ),
        (
            {"results": ["not-an-item-dict"]},
            "Data corruption detected: Received malformed memory item from storage layer.",
            "item_preview",
        ),
        (
            {"results": [{**_mem("tail-1"), "metadata": "not-a-dict"}]},
            "Data corruption detected: Received malformed metadata from storage layer.",
            "item_preview",
        ),
    ],
)
def test_adaptive_retry_malformed_response_raises_data_corruption_error(
    malformed_response, expected_message: str, expected_detail_key: str
):
    """Malformed retry payloads raise MemoryOperationError instead of falling back to batch 1."""
    service = MemoryReadService(
        _Client(
            [], per_call_responses=[_expired_heavy_first_batch(), malformed_response]
        )
    )

    with pytest.raises(MemoryOperationError) as exc_info:
        service.search_memories(
            query="Apollo",
            agent_id="agent-1",
            status="active",
            limit=5,
            _adaptive_fetch=True,
        )

    assert exc_info.value.message == expected_message
    assert expected_detail_key in exc_info.value.details
    assert [c["top_k"] for c in service.client.similarity_search.calls] == [
        25,
        MOORCHEH_MAX_TOP_K,
    ]
