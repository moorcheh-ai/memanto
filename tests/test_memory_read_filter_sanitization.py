from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService


def test_build_filtered_query_accepts_safe_filters():
    service = MemoryReadService(MagicMock())

    query = service._build_filtered_query(
        query="deployment notes",
        type=["fact"],
        tags=["prod-db"],
        metadata_filters={"source": "cli.import"},
    )

    assert query == "deployment notes #memory_type:fact #prod-db #source:cli.import"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": ["fact #status:expired"]},
        {"tags": ["prod #status:expired"]},
        {"metadata_filters": {"source": "cli #status:expired"}},
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
