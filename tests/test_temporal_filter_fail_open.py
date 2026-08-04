"""
Regression tests for the temporal filter fail-open behaviour.

When ``_apply_temporal_filter`` encounters a memory whose ``created_at``
field is missing or unparseable, the memory must be **kept** (fail open)
rather than silently dropped. Dropping it causes timeline amnesia — the
exact data-loss pattern that bounty #770 is designed to catch — and is
inconsistent with ``_filter_expired_memories``, which already fails open
on unparseable ``expires_at`` values.
"""

from memanto.app.services.memory_read_service import MemoryReadService


def _mem(mem_id: str, created_at: str | None = None) -> dict:
    """Build a minimal formatted memory item as returned by _format_memory_item."""
    return {
        "id": mem_id,
        "title": f"Memory {mem_id}",
        "content": "Some content",
        "text": f"[FACT] Memory {mem_id}",
        "type": "fact",
        "confidence": 0.9,
        "status": "active",
        "tags": [],
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": None,
        "ttl_seconds": None,
        "actor_id": "agent-1",
        "source": "user",
        "source_ref": None,
        "agent_id": "agent-1",
        "score": 1.0,
        "provenance": "explicit_statement",
    }


class _FakeClient:
    """Minimal client stub — _apply_temporal_filter is a pure post-filter."""

    pass


def _service():
    return MemoryReadService(_FakeClient())


def test_missing_created_at_is_kept_with_created_after():
    """A memory with no created_at must survive a created_after filter."""
    service = _service()
    results = [
        _mem("m1", "2026-06-01T00:00:00Z"),
        _mem("m2", None),  # missing timestamp
        _mem("m3", "2026-01-01T00:00:00Z"),  # before the cutoff
    ]

    filtered = service._apply_temporal_filter(
        results, created_after="2026-03-01T00:00:00Z"
    )

    ids = {m["id"] for m in filtered}
    assert "m1" in ids  # after cutoff: kept
    assert "m2" in ids  # missing timestamp: FAIL OPEN (kept)
    assert "m3" not in ids  # before cutoff: filtered out


def test_missing_created_at_is_kept_with_created_before():
    """A memory with no created_at must survive a created_before filter."""
    service = _service()
    results = [
        _mem("m1", "2026-01-01T00:00:00Z"),
        _mem("m2", None),  # missing timestamp
        _mem("m3", "2026-06-01T00:00:00Z"),  # after the cutoff
    ]

    filtered = service._apply_temporal_filter(
        results, created_before="2026-03-01T00:00:00Z"
    )

    ids = {m["id"] for m in filtered}
    assert "m1" in ids  # before cutoff: kept
    assert "m2" in ids  # missing timestamp: FAIL OPEN (kept)
    assert "m3" not in ids  # after cutoff: filtered out


def test_unparseable_created_at_is_kept():
    """A memory with a corrupt created_at string must survive temporal filtering."""
    service = _service()
    results = [
        _mem("m1", "2026-06-01T00:00:00Z"),
        _mem("m2", "not-a-timestamp"),  # corrupt timestamp
        _mem("m3", "2026-01-01T00:00:00Z"),  # before the cutoff
    ]

    filtered = service._apply_temporal_filter(
        results, created_after="2026-03-01T00:00:00Z"
    )

    ids = {m["id"] for m in filtered}
    assert "m1" in ids  # after cutoff: kept
    assert "m2" in ids  # corrupt timestamp: FAIL OPEN (kept)
    assert "m3" not in ids  # before cutoff: filtered out


def test_valid_timestamps_are_still_filtered_correctly():
    """Normal filtering behaviour must be preserved for valid timestamps."""
    service = _service()
    results = [
        _mem("m1", "2026-06-01T00:00:00Z"),
        _mem("m2", "2026-04-01T00:00:00Z"),
        _mem("m3", "2026-01-01T00:00:00Z"),
    ]

    filtered = service._apply_temporal_filter(
        results,
        created_after="2026-03-01T00:00:00Z",
        created_before="2026-05-01T00:00:00Z",
    )

    ids = {m["id"] for m in filtered}
    assert ids == {"m2"}  # only April memory is in range


def test_all_missing_timestamps_are_kept():
    """When every memory lacks a timestamp, all must survive temporal filtering."""
    service = _service()
    results = [
        _mem("m1", None),
        _mem("m2", None),
        _mem("m3", None),
    ]

    filtered = service._apply_temporal_filter(
        results, created_after="2026-01-01T00:00:00Z"
    )

    assert len(filtered) == 3
    assert {m["id"] for m in filtered} == {"m1", "m2", "m3"}
