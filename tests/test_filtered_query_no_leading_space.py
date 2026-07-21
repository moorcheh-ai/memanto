import pytest
from memanto.services.memory_read_service import MemoryReadService

class TestFilteredQueryNoLeadingSpace:
    def test_empty_query_with_filters(self):
        service = MemoryReadService()
        query = ""
        filters = ["#memory_type:fact", "#source:user"]
        result = service._build_filtered_query(query, filters)
        assert result == "#memory_type:fact #source:user"

    def test_whitespace_query_with_filters(self):
        service = MemoryReadService()
        query = "   "
        filters = ["#memory_type:fact", "#source:user"]
        result = service._build_filtered_query(query, filters)
        assert result == "#memory_type:fact #source:user"

    def test_query_with_leading_whitespace_and_filters(self):
        service = MemoryReadService()
        query = "   test query"
        filters = ["#memory_type:fact", "#source:user"]
        result = service._build_filtered_query(query, filters)
        assert result == "test query #memory_type:fact #source:user"

    def test_query_with_trailing_whitespace_and_filters(self):
        service = MemoryReadService()
        query = "test query   "
        filters = ["#memory_type:fact", "#source:user"]
        result = service._build_filtered_query(query, filters)
        assert result == "test query #memory_type:fact #source:user"

    def test_query_with_whitespace_and_filters(self):
        service = MemoryReadService()
        query = "   test query   "
        filters = ["#memory_type:fact", "#source:user"]
        result = service._build_filtered_query(query, filters)
        assert result == "test query #memory_type:fact #source:user"