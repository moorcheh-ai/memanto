"""Bounty #770 round 2 — reproducible regression tests for 4 more bugs.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round2.py -v
      (or:  python tests/failing_tests/test_bounty_770_round2.py)

Each test documents the bug it guards against; all fail on the pre-fix code
and pass on the fixed code.

Bugs covered:
1. HIGH: temporal recall limit slices with negative/zero silently return
   wrong result windows (Python negative-index slicing), inconsistent with
   search_memories' fail-closed validation.
2. MED:  _fetch_all_memories pagination loop has no protection against a
   repeated next_token from the storage layer -> unbounded HTTP loop.
3. MED:  search_memories reports total_found as the paginated window length
   instead of the post-filter match total, so clients using total_found to
   decide "are there more" / display counts get wrong numbers.
4. LOW:  generate_conflict_report hardcodes ~/.memanto/conflicts instead of
   honoring the configured data dir (get_data_dir), so conflict reports land
   in a different directory than summaries when MEMANTO_DATA_DIR is set.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


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


class _StuckPaginationClient:
    """Storage stub whose next_token never advances (bug 2 repro)."""

    def __init__(self):
        self.calls = 0
        self.documents = self

    def fetch_text_data(self, **kwargs):
        self.calls += 1
        return {
            "items": [_memory(f"m{self.calls}", "2026-01-15T09:00:00Z")],
            "pagination": {"has_more": True, "next_token": "stuck-token"},
        }


class _FakeDocuments:
    def __init__(self, items=None):
        self._items = items or [
            _memory("morning", "2026-01-15T09:00:00Z"),
            _memory("evening", "2026-01-15T18:00:00Z"),
            _memory("next-day", "2026-01-16T00:00:00Z"),
        ]

    def fetch_text_data(self, **kwargs):
        return {"items": self._items, "pagination": {"has_more": False}}


class _FakeClient:
    documents = _FakeDocuments()

    class _SimilaritySearch:
        def query(self, **kwargs):
            return {
                "results": [
                    {
                        "id": "morning",
                        "text": "[FACT] morning\n\nStored memory",
                        "score": 0.9,
                        "metadata": {
                            "memory_type": "fact",
                            "created_at": "2026-01-15T09:00:00Z",
                            "updated_at": "2026-01-15T09:00:00Z",
                            "confidence": 0.9,
                        },
                    },
                    {
                        "id": "evening",
                        "text": "[FACT] evening\n\nStored memory",
                        "score": 0.8,
                        "metadata": {
                            "memory_type": "fact",
                            "created_at": "2026-01-15T18:00:00Z",
                            "updated_at": "2026-01-15T18:00:00Z",
                            "confidence": 0.9,
                        },
                    },
                    {
                        "id": "next-day",
                        "text": "[FACT] next-day\n\nStored memory",
                        "score": 0.7,
                        "metadata": {
                            "memory_type": "fact",
                            "created_at": "2026-01-16T00:00:00Z",
                            "updated_at": "2026-01-16T00:00:00Z",
                            "confidence": 0.9,
                        },
                    },
                ]
            }

    similarity_search = _SimilaritySearch()


# ---------------------------------------------------------------------------
# 1. Temporal recall limit must reject negative/zero, not silently slice
# ---------------------------------------------------------------------------
def test_search_changed_since_rejects_negative_limit():
    """limit=-1 must raise ValueError (not a wrapped MemoryError), never
    silently return everything-but-the-last via Python negative-index
    slicing on the result list."""
    from memanto.app.services.memory_read_service import MemoryReadService

    svc = MemoryReadService(_FakeClient())
    try:
        svc.search_changed_since(
            since_date="2026-01-01T00:00:00Z",
            agent_id="agent-1",
            limit=-1,
        )
        raise AssertionError("expected an error for negative limit")
    except ValueError as e:
        assert "limit must be a positive integer" in str(e)


def test_search_recent_rejects_zero_limit():
    """limit=0 must raise ValueError, not return an empty window
    indistinguishable from 'no memories'."""
    from memanto.app.services.memory_read_service import MemoryReadService

    svc = MemoryReadService(_FakeClient())
    try:
        svc.search_recent(agent_id="agent-1", limit=0)
        raise AssertionError("expected an error for zero limit")
    except ValueError as e:
        assert "limit must be a positive integer" in str(e)


def test_search_as_of_rejects_negative_limit():
    """Same fail-closed contract for point-in-time recall."""
    from memanto.app.services.memory_read_service import MemoryReadService

    svc = MemoryReadService(_FakeClient())
    try:
        svc.search_as_of(as_of_date="2026-01-15", agent_id="agent-1", limit=-3)
        raise AssertionError("expected an error for negative limit")
    except ValueError as e:
        assert "limit must be a positive integer" in str(e)


# ---------------------------------------------------------------------------
# 2. Pagination loop must not spin forever on a repeated next_token
# ---------------------------------------------------------------------------
def test_fetch_all_memories_stops_on_repeated_next_token():
    """A storage layer that keeps returning has_more=True with the same
    next_token must not produce an unbounded fetch loop."""
    from memanto.app.services.memory_read_service import MemoryReadService

    client = _StuckPaginationClient()
    svc = MemoryReadService(client)
    # If the fix is absent this call loops until timeout/crash. With the fix
    # it returns after a bounded number of pages (stale token detected).
    result = svc._fetch_all_memories(["agent-1"])
    assert client.calls < 1000, "pagination loop did not terminate"
    assert len(result) >= 1  # still collected the first page


def test_fetch_all_memories_bounded_when_backend_keeps_paging():
    """Even a backend that legitimately pages many times cannot exceed a
    sane cap on total documents fetched."""
    from memanto.app.services.memory_read_service import MemoryReadService

    class _ManyPagesDocuments:
        def __init__(self):
            self.calls = 0

        def fetch_text_data(self, **kwargs):
            self.calls += 1
            return {
                "items": [_memory(f"m{self.calls}", "2026-01-15T09:00:00Z")],
                "pagination": {"has_more": True, "next_token": f"tok-{self.calls}"},
            }

    class _ManyPagesClient:
        documents = _ManyPagesDocuments()

    client = _ManyPagesClient()
    svc = MemoryReadService(client)
    result = svc._fetch_all_memories(["agent-1"])
    assert client.documents.calls <= 200, "page cap not enforced"
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 3. total_found must be the post-filter total, not the paginated window
# ---------------------------------------------------------------------------
def test_search_memories_total_found_is_match_total():
    """total_found must report how many memories matched the filters (before
    offset/limit), not the length of the returned page."""
    from memanto.app.services.memory_read_service import MemoryReadService

    svc = MemoryReadService(_FakeClient())
    result = svc.search_memories(query="x", agent_id="agent-1", limit=1, offset=0)
    # 3 memories exist; page length is 1, but total_found must be 3.
    assert result["total_found"] == 3, (
        f"total_found={result['total_found']} should be the match total, "
        f"total_available={result.get('total_available')}"
    )
    assert result["total_available"] == 3
    assert len(result["results"]) == 1


def test_search_memories_total_found_respects_filters():
    """Type/temporal filters shrink the total; total_found must reflect the
    filtered match count, not the page size."""
    from memanto.app.services.memory_read_service import MemoryReadService

    class _SingleTypeDocuments:
        def fetch_text_data(self, **kwargs):
            return {
                "items": [
                    _memory("fact-a", "2026-01-15T09:00:00Z"),
                    _memory("pref-b", "2026-01-15T10:00:00Z"),
                ],
                "pagination": {"has_more": False},
            }

    class _SingleTypeSimilarity:
        def query(self, **kwargs):
            # Simulate Moorcheh server-side #memory_type filtering: the
            # enhanced query for type=["preference"] carries the filter token,
            # and the backend only returns documents that match it.
            query = kwargs.get("query", "")
            rows = [
                {
                    "id": "fact-a",
                    "text": "[FACT] fact-a\n\nStored memory",
                    "score": 0.9,
                    "metadata": {
                        "memory_type": "fact",
                        "created_at": "2026-01-15T09:00:00Z",
                        "updated_at": "2026-01-15T09:00:00Z",
                        "confidence": 0.9,
                    },
                },
                {
                    "id": "pref-b",
                    "text": "[PREFERENCE] pref-b\n\nStored memory",
                    "score": 0.8,
                    "metadata": {
                        "memory_type": "preference",
                        "created_at": "2026-01-15T10:00:00Z",
                        "updated_at": "2026-01-15T10:00:00Z",
                        "confidence": 0.9,
                    },
                },
            ]
            if "#memory_type:preference" in query:
                rows = [r for r in rows if r["metadata"]["memory_type"] == "preference"]
            return {"results": rows}

    class _SingleTypeClient:
        documents = _SingleTypeDocuments()
        similarity_search = _SingleTypeSimilarity()

    svc = MemoryReadService(_SingleTypeClient())
    result = svc.search_memories(
        query="x", agent_id="agent-1", type=["preference"], limit=1
    )
    assert result["total_found"] == 1, (
        f"total_found={result['total_found']} should equal the filtered "
        f"match total (1 preference), not the page length"
    )


# ---------------------------------------------------------------------------
# 4. Conflict reports must honor the configured data dir
# ---------------------------------------------------------------------------
def test_conflict_report_uses_configured_data_dir():
    """generate_conflict_report must write into get_data_dir()/conflicts,
    not hardcoded ~/.memanto/conflicts, so a configured MEMANTO_DATA_DIR is
    respected consistently with summaries."""
    src = (
        Path(__file__).resolve().parents[2]
        / "memanto"
        / "app"
        / "services"
        / "daily_analysis_service.py"
    ).read_text(encoding="utf-8")
    # Split out just the generate_conflict_report function body.
    start = src.find("def generate_conflict_report")
    end = src.find("\n    def ", start + 10)
    body = src[start : end if end != -1 else len(src)]
    assert "Path.home()" not in body, (
        "generate_conflict_report hardcodes ~/.memanto instead of get_data_dir()"
    )
    assert "get_data_dir() / \"conflicts\"" in body


if __name__ == "__main__":
    tests = [
        test_search_changed_since_rejects_negative_limit,
        test_search_recent_rejects_zero_limit,
        test_search_as_of_rejects_negative_limit,
        test_fetch_all_memories_stops_on_repeated_next_token,
        test_fetch_all_memories_bounded_when_backend_keeps_paging,
        test_search_memories_total_found_is_match_total,
        test_search_memories_total_found_respects_filters,
        test_conflict_report_uses_configured_data_dir,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    sys.exit(1 if failures else 0)
