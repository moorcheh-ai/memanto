from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService


def test_build_filtered_query_accepts_safe_filters():
    service = MemoryReadService(MagicMock())

    query = service._build_filtered_query(
        query="deployment notes",
        type=["fact"],
        tags=["prod-db"],
        status_filter=["active"],
        metadata_filters={"source": "cli.import"},
    )

    assert query == (
        "deployment notes #memory_type:fact #prod-db #status:active #source:cli.import"
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": ["fact #status:deleted"]},
        {"tags": ["prod #status:deleted"]},
        {"status_filter": ["active #memory_type:error"]},
        {"metadata_filters": {"source": "cli #status:deleted"}},
        {"metadata_filters": {"source #status": "active"}},
    ],
)
def test_build_filtered_query_rejects_filter_clause_injection(kwargs):
    service = MemoryReadService(MagicMock())

    with pytest.raises(ValueError, match="Invalid"):
        service._build_filtered_query(query="deployment notes", **kwargs)


def test_build_filtered_query_rejects_unknown_memory_type():
    service = MemoryReadService(MagicMock())

    with pytest.raises(ValueError, match="Invalid memory_type"):
        service._build_filtered_query(query="deployment notes", type=["not-a-type"])


def test_temporal_filter_skips_malformed_result_timestamps():
    service = MemoryReadService(MagicMock())

    results = [
        {"id": "old", "created_at": "2024-01-01T00:00:00Z"},
        {"id": "malformed", "created_at": "not-a-timestamp"},
        {"id": "new", "created_at": "2026-01-01T00:00:00Z"},
    ]

    filtered = service._apply_temporal_filter(
        results, created_after="2025-01-01T00:00:00Z"
    )

    assert [result["id"] for result in filtered] == ["new"]


def test_temporal_filter_skips_malformed_result_timestamps_before_boundary():
    service = MemoryReadService(MagicMock())

    results = [
        {"id": "malformed", "created_at": "not-a-timestamp"},
        {"id": "old", "created_at": "2024-01-01T00:00:00Z"},
        {"id": "new", "created_at": "2026-01-01T00:00:00Z"},
    ]

    filtered = service._apply_temporal_filter(
        results, created_before="2025-01-01T00:00:00Z"
    )

    assert [result["id"] for result in filtered] == ["old"]
