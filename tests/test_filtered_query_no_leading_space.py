"""
Regression test for whitespace query handling in _build_filtered_query.
Ensures query.strip() is called before combining with filter_parts,
and that whitespace-only queries return only filter_parts.
"""

from unittest.mock import MagicMock
from memanto.app.services.memory_read_service import MemoryReadService


def _make_service():
    client = MagicMock()
    return MemoryReadService(moorcheh_client=client)


def test_empty_query_with_filter():
    service = _make_service()
    result = service._build_filtered_query(query="", status_filter=["active"])
    assert result == "#status:active"


def test_whitespace_query_with_filter():
    service = _make_service()
    result = service._build_filtered_query(query="   ", status_filter=["active"])
    assert result == "#status:active"


def test_whitespace_query_no_filter():
    service = _make_service()
    result = service._build_filtered_query(query="   ")
    assert result == ""


def test_normal_query_stripped():
    service = _make_service()
    result = service._build_filtered_query(query="  hello world  ", status_filter=["active"])
    assert "#status:active" in result
    assert result.startswith("hello world")
