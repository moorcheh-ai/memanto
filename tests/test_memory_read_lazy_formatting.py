"""
Tests for deferred presentation formatting in MemoryReadService.search_memories.

Validates that full document formatting (_format_memory_item) is deferred until
after candidate sorting, deduplication, and post-filtering, ensuring that at most
`limit` candidates are formatted rather than the full candidate pool.
"""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any
from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import (
    MOORCHEH_MAX_TOP_K,
    POST_FILTER_CANDIDATE_POOL,
    MemoryReadService,
)
from memanto.app.utils.errors import MemoryOperationError


def _raw_candidate(
    memory_id: str,
    memory_type: str = "fact",
    score: float = 0.9,
    status: str | None = "active",
    confidence: float | None = 0.85,
    created_at: str | int | float | None = "2026-06-15T12:00:00Z",
    tags: str = "general",
    nested_metadata: bool = True,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a raw backend candidate item mimicking Moorcheh API format."""
    item: dict[str, Any] = {
        "id": memory_id,
        "text": f"[{memory_type.upper()}] Title {memory_id}\n\nContent for {memory_id}\n\nTags: {tags}",
        "score": score,
    }
    if nested_metadata:
        metadata: dict[str, Any] = {
            "memory_type": memory_type,
            "tags": tags,
        }
        if status is not None:
            metadata["status"] = status
        if confidence is not None:
            metadata["confidence"] = confidence
        if created_at is not None:
            metadata["created_at"] = created_at
        if extra_fields:
            metadata.update(extra_fields)
        item["metadata"] = metadata
    else:
        # Legacy flat structure (no 'metadata' sub-dictionary)
        item["memory_type"] = memory_type
        item["tags"] = tags
        if status is not None:
            item["status"] = status
        if confidence is not None:
            item["confidence"] = confidence
        if created_at is not None:
            item["created_at"] = created_at
        if extra_fields:
            item.update(extra_fields)

    return item


class _StaticSimilaritySearch:
    """Mock similarity_search returning a pre-configured candidate list."""

    def __init__(self, candidates: list[dict[str, Any]]):
        self.candidates = candidates
        self.last_query = None
        self.last_kwargs = None

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        self.last_query = kwargs.get("query")
        top_k = kwargs.get("top_k", 100)
        return {"results": self.candidates[:top_k], "execution_time": 0.005}


class _FakeMoorchehClient:
    def __init__(self, candidates: list[dict[str, Any]]):
        self.similarity_search = _StaticSimilaritySearch(candidates)


class OriginalEagerMemoryReadService(MemoryReadService):
    """Reference implementation reproducing the original eager-formatting pipeline (HEAD~1).

    Formats all retrieved backend candidates upfront before sorting, deduplication,
    temporal filtering, status filtering, and min_confidence filtering.
    Used for side-by-side differential equivalence testing.
    """

    def search_memories(
        self,
        query: str,
        agent_id: str | None = None,
        type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
        status: str = "all",
        limit: int = 10,
        offset: int = 0,
        min_similarity_score: float | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        metadata_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        namespaces = self._get_search_namespaces(agent_id)
        if not namespaces:
            return {"results": [], "total_found": 0, "execution_time": 0}

        distinct_types = list(dict.fromkeys(type or []))
        type_variants: list[list[str] | None] = (
            [[memory_type] for memory_type in distinct_types]
            if len(distinct_types) > 1
            else [distinct_types or None]
        )
        enhanced_queries = [
            self._build_filtered_query(
                query=query,
                type=type_variant,
                tags=tags,
                min_confidence=min_confidence,
                created_after=created_after,
                created_before=created_before,
                metadata_filters=metadata_filters,
            )
            for type_variant in type_variants
        ]

        requested_limit = limit + offset
        needs_post_filter = (
            created_after is not None
            or created_before is not None
            or min_confidence is not None
            or status != "all"
        )
        if needs_post_filter:
            top_k = min(
                max(requested_limit, POST_FILTER_CANDIDATE_POOL), MOORCHEH_MAX_TOP_K
            )
        else:
            top_k = min(requested_limit, MOORCHEH_MAX_TOP_K)

        use_kiosk = min_similarity_score is not None and min_similarity_score > 0

        def _dispatch(enhanced_query: str) -> Any:
            return self.client.similarity_search.query(
                query=enhanced_query,
                namespaces=namespaces,
                top_k=top_k,
                threshold=min_similarity_score if use_kiosk else None,
                kiosk_mode=use_kiosk,
            )

        dispatch_start = monotonic()
        if len(enhanced_queries) == 1:
            search_results = [_dispatch(enhanced_queries[0])]
        else:
            max_workers = min(len(enhanced_queries), 8)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                search_results = list(pool.map(_dispatch, enhanced_queries))
        execution_time = monotonic() - dispatch_start

        search_items: list[Any] = []
        for search_result in search_results:
            if not isinstance(search_result, dict):
                try:
                    search_result = dict(search_result)
                except (TypeError, ValueError):
                    raise MemoryOperationError(
                        message="Data corruption detected: Received malformed search result from storage layer.",
                        details={"result_preview": str(search_result)[:100]},
                    )
            result_items = search_result.get("results", [])
            if not isinstance(result_items, list):
                raise MemoryOperationError(
                    message="Data corruption detected: Received malformed search result array from storage layer.",
                    details={"items_preview": str(result_items)[:100]},
                )
            search_items.extend(result_items)

        # Original eager formatting: format all items upfront
        all_results = [self._format_memory_item(item) for item in search_items]

        if len(enhanced_queries) > 1:
            def _score(memory: dict[str, Any]) -> float:
                raw_score = memory.get("score")
                if raw_score is None:
                    return float("-inf")
                try:
                    return float(raw_score)
                except (TypeError, ValueError):
                    return float("-inf")

            all_results.sort(key=_score, reverse=True)
            unique_results: list[dict[str, Any]] = []
            seen_ids: set[Any] = set()
            for memory in all_results:
                memory_id = memory.get("id")
                if memory_id is not None and memory_id in seen_ids:
                    continue
                if memory_id is not None:
                    seen_ids.add(memory_id)
                unique_results.append(memory)
            all_results = unique_results

        if created_after or created_before:
            all_results = self._apply_temporal_filter(
                all_results,
                created_after=created_after,
                created_before=created_before,
            )

        all_results = self._filter_by_status(all_results, status)

        if min_confidence is not None:
            all_results = self._filter_by_min_confidence(
                all_results, min_confidence
            )

        paginated_results = all_results[offset: offset + limit]
        has_more = len(all_results) > offset + limit

        return {
            "results": paginated_results,
            "total_found": len(paginated_results),
            "total_available": len(all_results),
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "query": query,
            "enhanced_query": " OR ".join(enhanced_queries),
            "execution_time": execution_time,
        }


def test_lazy_formatting_bounds_formatting_calls_to_limit():
    """Verify that with 100 candidates and limit=10, at most 10 undergo full presentation formatting."""
    candidates = [
        _raw_candidate(f"mem-{i}", score=0.99 - (i * 0.005))
        for i in range(100)
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    original_format = service._format_memory_item
    format_call_count = 0

    def format_spy(item):
        nonlocal format_call_count
        format_call_count += 1
        return original_format(item)

    service._format_memory_item = format_spy

    result = service.search_memories(
        query="test query",
        agent_id="agent-1",
        limit=10,
        status="active",
    )

    assert len(result["results"]) == 10
    assert result["total_found"] == 10
    assert result["total_available"] == 100
    assert format_call_count <= 10
    assert format_call_count == 10


def test_lazy_formatting_bounds_formatting_when_candidates_filtered():
    """When filters discard candidates, only surviving candidates in the slice are formatted."""
    # 100 candidates: only 4 have status="active"
    candidates = [
        _raw_candidate(
            f"mem-{i}",
            status="active" if i < 4 else "expired",
            score=0.99 - (i * 0.005),
        )
        for i in range(100)
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    format_call_count = 0
    orig_format = service._format_memory_item

    def spy_format(item):
        nonlocal format_call_count
        format_call_count += 1
        return orig_format(item)

    service._format_memory_item = spy_format

    result = service.search_memories(
        query="test query",
        agent_id="agent-1",
        limit=10,
        status="active",
    )

    assert len(result["results"]) == 4
    assert result["total_found"] == 4
    assert result["total_available"] == 4
    assert format_call_count == 4


def test_lazy_formatting_status_filtering_including_legacy():
    """Status filtering works on raw candidates, treating absent status as 'active'."""
    candidates = [
        _raw_candidate("active-1", status="active", score=0.9),
        _raw_candidate("legacy-active", status=None, score=0.85),
        _raw_candidate("expired-1", status="expired", score=0.8),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    result_active = service.search_memories(
        query="test", agent_id="agent-1", status="active", limit=10
    )
    active_ids = [m["id"] for m in result_active["results"]]
    assert active_ids == ["active-1", "legacy-active"]
    assert result_active["total_available"] == 2

    result_expired = service.search_memories(
        query="test", agent_id="agent-1", status="expired", limit=10
    )
    expired_ids = [m["id"] for m in result_expired["results"]]
    assert expired_ids == ["expired-1"]
    assert result_expired["total_available"] == 1


def test_lazy_formatting_confidence_filtering():
    """Confidence filtering works on raw candidates and fails open for missing/unparseable values."""
    candidates = [
        _raw_candidate("high-conf", confidence=0.95, score=0.9),
        _raw_candidate("low-conf", confidence=0.30, score=0.85),
        _raw_candidate("no-conf", confidence=None, score=0.80),
        _raw_candidate("unparseable-conf", confidence="not-a-number", score=0.75),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    result = service.search_memories(
        query="test", agent_id="agent-1", min_confidence=0.8, limit=10
    )
    ids = [m["id"] for m in result["results"]]
    assert ids == ["high-conf", "no-conf", "unparseable-conf"]
    assert result["total_available"] == 3


def test_lazy_formatting_temporal_filtering():
    """Temporal filtering works on raw candidates with ISO strings and epoch numbers."""
    candidates = [
        _raw_candidate("in-window-iso", created_at="2026-06-15T12:00:00Z", score=0.9),
        _raw_candidate("in-window-epoch", created_at=1781524800, score=0.85),  # 2026-06-16T12:00:00
        _raw_candidate("too-early", created_at="2026-05-01T00:00:00Z", score=0.8),
        _raw_candidate("too-late", created_at="2026-07-01T00:00:00Z", score=0.75),
        _raw_candidate("bad-date", created_at="invalid-date", score=0.7),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    result = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_after="2026-06-01T00:00:00Z",
        created_before="2026-06-30T23:59:59Z",
        limit=10,
    )
    ids = [m["id"] for m in result["results"]]
    assert ids == ["in-window-iso", "in-window-epoch"]
    assert result["total_available"] == 2


def test_lazy_formatting_multi_type_dedup_and_scores():
    """Multi-type queries correctly sort raw candidates by score DESC and deduplicate by ID."""
    type_responses = {
        "fact": [
            _raw_candidate("dup-1", memory_type="fact", score=0.70),
            _raw_candidate("fact-only", memory_type="fact", score=0.80),
        ],
        "preference": [
            _raw_candidate("dup-1", memory_type="preference", score=0.95),  # Higher score
            _raw_candidate("pref-only", memory_type="preference", score=0.60),
        ],
    }

    class _MultiTypeSearch:
        def query(self, **kwargs):
            query = kwargs.get("query", "")
            if "#memory_type:fact" in query:
                return {"results": type_responses["fact"], "execution_time": 0.001}
            elif "#memory_type:preference" in query:
                return {"results": type_responses["preference"], "execution_time": 0.001}
            return {"results": [], "execution_time": 0.001}

    mock_client = MagicMock()
    mock_client.similarity_search = _MultiTypeSearch()
    service = MemoryReadService(mock_client)

    result = service.search_memories(
        query="project",
        agent_id="agent-1",
        type=["fact", "preference"],
        limit=10,
    )

    ids = [m["id"] for m in result["results"]]
    # dup-1 (score 0.95 from preference) should be first and deduplicated, then fact-only (0.80), then pref-only (0.60)
    assert ids == ["dup-1", "fact-only", "pref-only"]
    assert result["results"][0]["score"] == 0.95
    assert result["total_available"] == 3


def test_lazy_formatting_with_offset():
    """Offset slices raw candidates correctly and only formats the requested page."""
    candidates = [
        _raw_candidate(f"mem-{i}", score=0.99 - (i * 0.005))
        for i in range(50)
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    format_calls = 0
    orig_format = service._format_memory_item

    def spy_format(item):
        nonlocal format_calls
        format_calls += 1
        return orig_format(item)

    service._format_memory_item = spy_format

    # 1. Unfiltered: requested_limit = offset + limit = 10 + 5 = 15 candidates fetched
    result = service.search_memories(
        query="test",
        agent_id="agent-1",
        offset=10,
        limit=5,
    )

    assert [m["id"] for m in result["results"]] == [f"mem-{i}" for i in range(10, 15)]
    assert result["total_found"] == 5
    assert result["total_available"] == 15
    assert result["offset"] == 10
    assert result["limit"] == 5
    assert result["has_more"] is False
    assert format_calls == 5

    # 2. Filtered (status="active"): candidate pool widened to 50
    format_calls = 0
    result_filtered = service.search_memories(
        query="test",
        agent_id="agent-1",
        status="active",
        offset=10,
        limit=5,
    )
    assert [m["id"] for m in result_filtered["results"]] == [f"mem-{i}" for i in range(10, 15)]
    assert result_filtered["total_found"] == 5
    assert result_filtered["total_available"] == 50
    assert result_filtered["offset"] == 10
    assert result_filtered["limit"] == 5
    assert result_filtered["has_more"] is True
    assert format_calls == 5


def test_lazy_formatting_preserves_legacy_flat_metadata():
    """Legacy documents with flat field structure are parsed and formatted identically."""
    candidates = [
        _raw_candidate("flat-item", nested_metadata=False, status="active", confidence=0.88),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    result = service.search_memories(query="test", agent_id="agent-1", limit=1)
    item = result["results"][0]

    assert item["id"] == "flat-item"
    assert item["type"] == "fact"
    assert item["status"] == "active"
    assert item["confidence"] == 0.88


def test_lazy_formatting_detects_data_corruption_in_raw_item():
    """Corrupted raw items raise MemoryOperationError upfront."""
    client = _FakeMoorchehClient(["not-a-dict"])
    service = MemoryReadService(client)

    with pytest.raises(MemoryOperationError, match="Data corruption detected"):
        service.search_memories(query="test", agent_id="agent-1")


def test_lazy_formatting_detects_data_corruption_in_metadata():
    """Corrupted metadata structures raise MemoryOperationError upfront."""
    client = _FakeMoorchehClient([{"id": "bad-meta", "text": "foo", "metadata": "not-a-dict"}])
    service = MemoryReadService(client)

    with pytest.raises(MemoryOperationError, match="Data corruption detected"):
        service.search_memories(query="test", agent_id="agent-1")


def test_lazy_formatting_epoch_zero_int_and_float_timestamps():
    """Regression test: Unix epoch 0 (int) and 0.0 (float) survive created_before filters.

    Ensures falsy numeric values (0 and 0.0) are coerced into ISO string
    '1970-01-01T00:00:00+00:00' and not discarded by falsy checks.
    """
    candidates = [
        _raw_candidate("epoch-int-zero", created_at=0, score=0.95),
        _raw_candidate("epoch-float-zero", created_at=0.0, score=0.90),
        _raw_candidate("epoch-valid-past", created_at=1577836800, score=0.85),  # 2020-01-01
        _raw_candidate("modern-item", created_at="2026-06-15T12:00:00Z", score=0.80),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # Filter with created_before="1980-01-01T00:00:00Z":
    # Only epoch 0 (int) and 0.0 (float) must survive.
    result = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="1980-01-01T00:00:00Z",
        limit=10,
    )
    ids = [m["id"] for m in result["results"]]
    assert ids == ["epoch-int-zero", "epoch-float-zero"]
    assert result["total_available"] == 2
    assert result["results"][0]["created_at"] == "1970-01-01T00:00:00+00:00"
    assert result["results"][1]["created_at"] == "1970-01-01T00:00:00+00:00"

    # Filter with created_before="2021-01-01T00:00:00Z":
    # Epoch 0 (int), 0.0 (float), and 1577836800 (2020) must survive; modern-item (2026) excluded.
    result_2021 = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="2021-01-01T00:00:00Z",
        limit=10,
    )
    ids_2021 = [m["id"] for m in result_2021["results"]]
    assert ids_2021 == ["epoch-int-zero", "epoch-float-zero", "epoch-valid-past"]
    assert result_2021["total_available"] == 3


def test_lazy_formatting_metadata_none_fallback_to_flat_status():
    """Regression test: metadata={'status': None} correctly falls back to flat status."""
    candidates = [
        {
            "id": "status-fallback-expired",
            "text": "[FACT] Expired memory\n\nContent",
            "score": 0.9,
            "status": "expired",
            "metadata": {"status": None, "memory_type": "fact"},
        },
        {
            "id": "status-fallback-active",
            "text": "[FACT] Active memory\n\nContent",
            "score": 0.85,
            "status": "active",
            "metadata": {"status": None, "memory_type": "fact"},
        },
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # Query for active
    res_active = service.search_memories(
        query="test", agent_id="agent-1", status="active", limit=10
    )
    assert [m["id"] for m in res_active["results"]] == ["status-fallback-active"]
    assert res_active["results"][0]["status"] == "active"

    # Query for expired
    res_expired = service.search_memories(
        query="test", agent_id="agent-1", status="expired", limit=10
    )
    assert [m["id"] for m in res_expired["results"]] == ["status-fallback-expired"]
    assert res_expired["results"][0]["status"] == "expired"


def test_lazy_formatting_metadata_none_fallback_to_flat_confidence():
    """Regression test: metadata={'confidence': None} correctly falls back to flat confidence."""
    candidates = [
        {
            "id": "conf-fallback-high",
            "text": "[FACT] High conf\n\nContent",
            "score": 0.9,
            "confidence": 0.95,
            "metadata": {"confidence": None, "memory_type": "fact"},
        },
        {
            "id": "conf-fallback-low",
            "text": "[FACT] Low conf\n\nContent",
            "score": 0.85,
            "confidence": 0.40,
            "metadata": {"confidence": None, "memory_type": "fact"},
        },
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    res = service.search_memories(
        query="test", agent_id="agent-1", min_confidence=0.8, limit=10
    )
    # High conf survives (0.95 >= 0.8), low conf excluded (0.40 < 0.8)
    assert [m["id"] for m in res["results"]] == ["conf-fallback-high"]
    assert res["results"][0]["confidence"] == 0.95


def test_lazy_formatting_missing_and_empty_timestamps():
    """Regression test: missing and empty timestamp behavior remains identical.

    - Under temporal filters, missing/None/empty timestamps are excluded (fail-closed).
    - Without temporal filters, missing/None/empty timestamps are preserved in output.
    """
    candidates = [
        # 1. Missing created_at key entirely
        {"id": "no-key", "text": "No key", "score": 0.9, "metadata": {"memory_type": "fact"}},
        # 2. Nested None
        {"id": "nested-none", "text": "None ts", "score": 0.85, "metadata": {"created_at": None, "memory_type": "fact"}},
        # 3. Nested empty string
        {"id": "nested-empty", "text": "Empty ts", "score": 0.80, "metadata": {"created_at": "", "memory_type": "fact"}},
        # 4. Flat empty string
        {"id": "flat-empty", "text": "Flat empty", "score": 0.75, "created_at": "", "memory_type": "fact"},
        # 5. Valid timestamp
        {"id": "valid-ts", "text": "Valid ts", "score": 0.70, "created_at": "2026-06-15T12:00:00Z", "memory_type": "fact"},
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # With temporal filter: only valid-ts survives
    res_temporal = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="2026-12-31T23:59:59Z",
        limit=10,
    )
    assert [m["id"] for m in res_temporal["results"]] == ["valid-ts"]
    assert res_temporal["total_available"] == 1

    # Without temporal filter: all 5 survive, preserving missing/empty values
    res_unfiltered = service.search_memories(
        query="test",
        agent_id="agent-1",
        status="all",
        limit=10,
    )
    assert len(res_unfiltered["results"]) == 5
    by_id = {m["id"]: m for m in res_unfiltered["results"]}
    assert by_id["no-key"]["created_at"] is None
    assert by_id["nested-none"]["created_at"] is None
    assert by_id["nested-empty"]["created_at"] == ""
    assert by_id["flat-empty"]["created_at"] == ""
    assert by_id["valid-ts"]["created_at"] == "2026-06-15T12:00:00Z"


def test_lazy_formatting_differential_side_by_side_equivalence():
    """Side-by-side differential test comparing eager vs lazy output across varied queries.

    Compares the complete response structure (not just result IDs) between the original
    eager pipeline (OriginalEagerMemoryReadService) and the optimized lazy pipeline.
    Covers:
    - Mixed metadata layouts (nested, flat, explicit None fallback, custom attributes)
    - Duplicate IDs with varying scores across types
    - Missing fields (status, confidence, score, timestamps)
    - Multiple memory types
    - Pagination offsets and limits
    - Status and temporal filter combinations
    """
    raw_fact_candidates: list[dict[str, Any]] = []
    raw_pref_candidates: list[dict[str, Any]] = []

    for i in range(100):
        # Create fact candidates
        c_fact = _raw_candidate(
            memory_id=f"mem-{i}",
            memory_type="fact",
            score=0.99 - (i * 0.008),
            status="active" if i % 3 != 0 else "expired",
            confidence=0.85 if i % 4 != 0 else 0.45,
            created_at=0 if i == 0 else (
                0.0 if i == 1 else (
                    f"2026-06-{(i % 25) + 1:02d}T12:00:00Z" if i % 5 != 0 else 1780000000 + i * 1000
                )
            ),
            nested_metadata=(i % 2 == 0),
            extra_fields={"custom_prop": f"prop-{i}"} if i % 5 == 0 else None,
        )
        raw_fact_candidates.append(c_fact)

        # Create preference candidates with some duplicate IDs with different scores
        c_pref = _raw_candidate(
            memory_id=f"mem-{i}" if i % 10 == 0 else f"pref-{i}",
            memory_type="preference",
            score=0.95 - (i * 0.007),
            status="active" if i % 2 == 0 else "expired",
            confidence=0.90 if i % 3 != 0 else 0.50,
            created_at=f"2026-06-{(i % 20) + 1:02d}T10:00:00Z",
            nested_metadata=(i % 3 != 0),
        )
        raw_pref_candidates.append(c_pref)

    class _DifferentialMoorchehClient:
        def __init__(self, facts, prefs):
            self.facts = facts
            self.prefs = prefs
            self.similarity_search = self

        def query(self, **kwargs):
            query_str = kwargs.get("query", "")
            top_k = kwargs.get("top_k", 100)
            if "#memory_type:preference" in query_str:
                items = self.prefs
            else:
                items = self.facts
            return {"results": items[:top_k], "execution_time": 0.001}

    mock_client = _DifferentialMoorchehClient(raw_fact_candidates, raw_pref_candidates)
    eager_service = OriginalEagerMemoryReadService(mock_client)
    lazy_service = MemoryReadService(mock_client)

    test_matrix = [
        # 1. Unfiltered single type
        {"type": ["fact"], "status": "all", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 10},
        # 2. Active status filter with offset
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": None, "created_before": None, "offset": 10, "limit": 10},
        # 3. Expired status filter
        {"type": ["fact"], "status": "expired", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 15},
        # 4. Temporal filter including epoch 0/0.0
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": None, "created_before": "1980-01-01T00:00:00Z", "offset": 0, "limit": 10},
        # 5. Temporal filter modern window
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": "2026-06-05T00:00:00Z", "created_before": "2026-06-20T00:00:00Z", "offset": 5, "limit": 10},
        # 6. Confidence filter
        {"type": ["fact"], "status": "active", "min_confidence": 0.8, "created_after": None, "created_before": None, "offset": 0, "limit": 20},
        # 7. Multi-type union with deduplication and score re-ranking
        {"type": ["fact", "preference"], "status": "active", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 15},
        # 8. Multi-type union with pagination offset
        {"type": ["fact", "preference"], "status": "active", "min_confidence": 0.7, "created_after": "2026-06-01T00:00:00Z", "created_before": "2026-06-30T00:00:00Z", "offset": 5, "limit": 10},
        # 9. Large offset beyond available results
        {"type": ["fact"], "status": "active", "min_confidence": 0.99, "created_after": None, "created_before": None, "offset": 50, "limit": 10},
    ]

    for params in test_matrix:
        eager_res = eager_service.search_memories(
            query="test recall",
            agent_id="test-agent",
            **params,
        )
        lazy_res = lazy_service.search_memories(
            query="test recall",
            agent_id="test-agent",
            **params,
        )

        # Assert complete structural equivalence
        assert lazy_res["total_found"] == eager_res["total_found"]
        assert lazy_res["total_available"] == eager_res["total_available"]
        assert lazy_res["offset"] == eager_res["offset"]
        assert lazy_res["limit"] == eager_res["limit"]
        assert lazy_res["has_more"] == eager_res["has_more"]
        assert lazy_res["query"] == eager_res["query"]
        assert lazy_res["enhanced_query"] == eager_res["enhanced_query"]
        assert lazy_res["results"] == eager_res["results"]


def test_lazy_formatting_epoch_zero_int_and_float_timestamps():
    """Regression test: Unix epoch 0 (int) and 0.0 (float) survive created_before filters.

    Ensures falsy numeric values (0 and 0.0) are coerced into ISO string
    '1970-01-01T00:00:00+00:00' and not discarded by falsy checks.
    """
    candidates = [
        _raw_candidate("epoch-int-zero", created_at=0, score=0.95),
        _raw_candidate("epoch-float-zero", created_at=0.0, score=0.90),
        _raw_candidate("epoch-valid-past", created_at=1577836800, score=0.85),  # 2020-01-01
        _raw_candidate("modern-item", created_at="2026-06-15T12:00:00Z", score=0.80),
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # Filter with created_before="1980-01-01T00:00:00Z":
    # Only epoch 0 (int) and 0.0 (float) must survive.
    result = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="1980-01-01T00:00:00Z",
        limit=10,
    )
    ids = [m["id"] for m in result["results"]]
    assert ids == ["epoch-int-zero", "epoch-float-zero"]
    assert result["total_available"] == 2
    assert result["results"][0]["created_at"] == "1970-01-01T00:00:00+00:00"
    assert result["results"][1]["created_at"] == "1970-01-01T00:00:00+00:00"

    # Filter with created_before="2021-01-01T00:00:00Z":
    # Epoch 0 (int), 0.0 (float), and 1577836800 (2020) must survive; modern-item (2026) excluded.
    result_2021 = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="2021-01-01T00:00:00Z",
        limit=10,
    )
    ids_2021 = [m["id"] for m in result_2021["results"]]
    assert ids_2021 == ["epoch-int-zero", "epoch-float-zero", "epoch-valid-past"]
    assert result_2021["total_available"] == 3


def test_lazy_formatting_metadata_none_fallback_to_flat_status():
    """Regression test: metadata={'status': None} correctly falls back to flat status."""
    candidates = [
        {
            "id": "status-fallback-expired",
            "text": "[FACT] Expired memory\n\nContent",
            "score": 0.9,
            "status": "expired",
            "metadata": {"status": None, "memory_type": "fact"},
        },
        {
            "id": "status-fallback-active",
            "text": "[FACT] Active memory\n\nContent",
            "score": 0.85,
            "status": "active",
            "metadata": {"status": None, "memory_type": "fact"},
        },
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # Query for active
    res_active = service.search_memories(
        query="test", agent_id="agent-1", status="active", limit=10
    )
    assert [m["id"] for m in res_active["results"]] == ["status-fallback-active"]
    assert res_active["results"][0]["status"] == "active"

    # Query for expired
    res_expired = service.search_memories(
        query="test", agent_id="agent-1", status="expired", limit=10
    )
    assert [m["id"] for m in res_expired["results"]] == ["status-fallback-expired"]
    assert res_expired["results"][0]["status"] == "expired"


def test_lazy_formatting_metadata_none_fallback_to_flat_confidence():
    """Regression test: metadata={'confidence': None} correctly falls back to flat confidence."""
    candidates = [
        {
            "id": "conf-fallback-high",
            "text": "[FACT] High conf\n\nContent",
            "score": 0.9,
            "confidence": 0.95,
            "metadata": {"confidence": None, "memory_type": "fact"},
        },
        {
            "id": "conf-fallback-low",
            "text": "[FACT] Low conf\n\nContent",
            "score": 0.85,
            "confidence": 0.40,
            "metadata": {"confidence": None, "memory_type": "fact"},
        },
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    res = service.search_memories(
        query="test", agent_id="agent-1", min_confidence=0.8, limit=10
    )
    # High conf survives (0.95 >= 0.8), low conf excluded (0.40 < 0.8)
    assert [m["id"] for m in res["results"]] == ["conf-fallback-high"]
    assert res["results"][0]["confidence"] == 0.95


def test_lazy_formatting_missing_and_empty_timestamps():
    """Regression test: missing and empty timestamp behavior remains identical.

    - Under temporal filters, missing/None/empty timestamps are excluded (fail-closed).
    - Without temporal filters, missing/None/empty timestamps are preserved in output.
    """
    candidates = [
        # 1. Missing created_at key entirely
        {"id": "no-key", "text": "No key", "score": 0.9, "metadata": {"memory_type": "fact"}},
        # 2. Nested None
        {"id": "nested-none", "text": "None ts", "score": 0.85, "metadata": {"created_at": None, "memory_type": "fact"}},
        # 3. Nested empty string
        {"id": "nested-empty", "text": "Empty ts", "score": 0.80, "metadata": {"created_at": "", "memory_type": "fact"}},
        # 4. Flat empty string
        {"id": "flat-empty", "text": "Flat empty", "score": 0.75, "created_at": "", "memory_type": "fact"},
        # 5. Valid timestamp
        {"id": "valid-ts", "text": "Valid ts", "score": 0.70, "created_at": "2026-06-15T12:00:00Z", "memory_type": "fact"},
    ]
    client = _FakeMoorchehClient(candidates)
    service = MemoryReadService(client)

    # With temporal filter: only valid-ts survives
    res_temporal = service.search_memories(
        query="test",
        agent_id="agent-1",
        created_before="2026-12-31T23:59:59Z",
        limit=10,
    )
    assert [m["id"] for m in res_temporal["results"]] == ["valid-ts"]
    assert res_temporal["total_available"] == 1

    # Without temporal filter: all 5 survive, preserving missing/empty values
    res_unfiltered = service.search_memories(
        query="test",
        agent_id="agent-1",
        status="all",
        limit=10,
    )
    assert len(res_unfiltered["results"]) == 5
    by_id = {m["id"]: m for m in res_unfiltered["results"]}
    assert by_id["no-key"]["created_at"] is None
    assert by_id["nested-none"]["created_at"] is None
    assert by_id["nested-empty"]["created_at"] == ""
    assert by_id["flat-empty"]["created_at"] == ""
    assert by_id["valid-ts"]["created_at"] == "2026-06-15T12:00:00Z"


def test_lazy_formatting_differential_side_by_side_equivalence():
    """Side-by-side differential test comparing eager vs lazy output across varied queries.

    Compares the complete response structure (not just result IDs) between the original
    eager pipeline (OriginalEagerMemoryReadService) and the optimized lazy pipeline.
    Covers:
    - Mixed metadata layouts (nested, flat, explicit None fallback, custom attributes)
    - Duplicate IDs with varying scores across types
    - Missing fields (status, confidence, score, timestamps)
    - Multiple memory types
    - Pagination offsets and limits
    - Status and temporal filter combinations
    """
    raw_fact_candidates: list[dict[str, Any]] = []
    raw_pref_candidates: list[dict[str, Any]] = []

    for i in range(100):
        # Create fact candidates
        c_fact = _raw_candidate(
            memory_id=f"mem-{i}",
            memory_type="fact",
            score=0.99 - (i * 0.008),
            status="active" if i % 3 != 0 else "expired",
            confidence=0.85 if i % 4 != 0 else 0.45,
            created_at=0 if i == 0 else (
                0.0 if i == 1 else (
                    f"2026-06-{(i % 25) + 1:02d}T12:00:00Z" if i % 5 != 0 else 1780000000 + i * 1000
                )
            ),
            nested_metadata=(i % 2 == 0),
            extra_fields={"custom_prop": f"prop-{i}"} if i % 5 == 0 else None,
        )
        raw_fact_candidates.append(c_fact)

        # Create preference candidates with some duplicate IDs with different scores
        c_pref = _raw_candidate(
            memory_id=f"mem-{i}" if i % 10 == 0 else f"pref-{i}",
            memory_type="preference",
            score=0.95 - (i * 0.007),
            status="active" if i % 2 == 0 else "expired",
            confidence=0.90 if i % 3 != 0 else 0.50,
            created_at=f"2026-06-{(i % 20) + 1:02d}T10:00:00Z",
            nested_metadata=(i % 3 != 0),
        )
        raw_pref_candidates.append(c_pref)

    class _DifferentialMoorchehClient:
        def __init__(self, facts, prefs):
            self.facts = facts
            self.prefs = prefs
            self.similarity_search = self

        def query(self, **kwargs):
            query_str = kwargs.get("query", "")
            top_k = kwargs.get("top_k", 100)
            if "#memory_type:preference" in query_str:
                items = self.prefs
            else:
                items = self.facts
            return {"results": items[:top_k], "execution_time": 0.001}

    mock_client = _DifferentialMoorchehClient(raw_fact_candidates, raw_pref_candidates)
    eager_service = OriginalEagerMemoryReadService(mock_client)
    lazy_service = MemoryReadService(mock_client)

    test_matrix = [
        # 1. Unfiltered single type
        {"type": ["fact"], "status": "all", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 10},
        # 2. Active status filter with offset
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": None, "created_before": None, "offset": 10, "limit": 10},
        # 3. Expired status filter
        {"type": ["fact"], "status": "expired", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 15},
        # 4. Temporal filter including epoch 0/0.0
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": None, "created_before": "1980-01-01T00:00:00Z", "offset": 0, "limit": 10},
        # 5. Temporal filter modern window
        {"type": ["fact"], "status": "active", "min_confidence": None, "created_after": "2026-06-05T00:00:00Z", "created_before": "2026-06-20T00:00:00Z", "offset": 5, "limit": 10},
        # 6. Confidence filter
        {"type": ["fact"], "status": "active", "min_confidence": 0.8, "created_after": None, "created_before": None, "offset": 0, "limit": 20},
        # 7. Multi-type union with deduplication and score re-ranking
        {"type": ["fact", "preference"], "status": "active", "min_confidence": None, "created_after": None, "created_before": None, "offset": 0, "limit": 15},
        # 8. Multi-type union with pagination offset
        {"type": ["fact", "preference"], "status": "active", "min_confidence": 0.7, "created_after": "2026-06-01T00:00:00Z", "created_before": "2026-06-30T00:00:00Z", "offset": 5, "limit": 10},
        # 9. Large offset beyond available results
        {"type": ["fact"], "status": "active", "min_confidence": 0.99, "created_after": None, "created_before": None, "offset": 50, "limit": 10},
    ]

    for params in test_matrix:
        eager_res = eager_service.search_memories(
            query="test recall",
            agent_id="test-agent",
            **params,
        )
        lazy_res = lazy_service.search_memories(
            query="test recall",
            agent_id="test-agent",
            **params,
        )

        # Assert complete structural equivalence
        assert lazy_res["total_found"] == eager_res["total_found"]
        assert lazy_res["total_available"] == eager_res["total_available"]
        assert lazy_res["offset"] == eager_res["offset"]
        assert lazy_res["limit"] == eager_res["limit"]
        assert lazy_res["has_more"] == eager_res["has_more"]
        assert lazy_res["query"] == eager_res["query"]
        assert lazy_res["enhanced_query"] == eager_res["enhanced_query"]
        assert lazy_res["results"] == eager_res["results"]
