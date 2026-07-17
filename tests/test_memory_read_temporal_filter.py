from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService


def _results():
    return [
        {"id": "old", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "new", "created_at": "2026-12-01T00:00:00Z"},
    ]


def test_created_after_filters_correctly():
    service = MemoryReadService(MagicMock())

    out = service._apply_temporal_filter(
        _results(), created_after="2026-06-01T00:00:00Z"
    )

    assert [r["id"] for r in out] == ["new"]


def test_created_before_filters_correctly():
    service = MemoryReadService(MagicMock())

    out = service._apply_temporal_filter(
        _results(), created_before="2026-06-01T00:00:00Z"
    )

    assert [r["id"] for r in out] == ["old"]


def test_single_malformed_record_does_not_disable_filter():
    """A single unparseable created_at must not silently return every memory.

    Regression: the previous implementation wrapped the whole comprehension in
    try/except and `pass`ed on error, so one bad record made the filter return
    the full, unfiltered result set.
    """
    service = MemoryReadService(MagicMock())
    results = [
        {"id": "old", "created_at": "2026-01-01T00:00:00Z"},
        {"id": "bad", "created_at": "GARBAGE"},
        {"id": "new", "created_at": "2026-12-01T00:00:00Z"},
    ]

    out = service._apply_temporal_filter(
        results, created_after="2026-06-01T00:00:00Z"
    )

    assert [r["id"] for r in out] == ["new"]


def test_invalid_boundary_raises_instead_of_over_returning():
    """A malformed caller-supplied boundary is a hard error, not a no-op.

    Silently ignoring it would over-return data the caller asked to exclude.
    """
    service = MemoryReadService(MagicMock())

    with pytest.raises(ValueError):
        service._apply_temporal_filter(_results(), created_after="not-a-date")

    with pytest.raises(ValueError):
        service._apply_temporal_filter(_results(), created_before="not-a-date")
