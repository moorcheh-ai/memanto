from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import (
    MemoryReadService,
    _sanitize_query_text,
)


def test_sanitize_query_text_neutralizes_filter_tags():
    # Leading # on tokens is stripped
    assert _sanitize_query_text("#status:expired") == "status:expired"
    assert (
        _sanitize_query_text("deployment notes #status:expired #source:admin")
        == "deployment notes status:expired source:admin"
    )
    assert _sanitize_query_text("###urgent") == "urgent"
    assert _sanitize_query_text("#memory_type:fact") == "memory_type:fact"


def test_sanitize_query_text_preserves_trailing_hash():
    # Trailing # like C# or F# should remain intact
    assert _sanitize_query_text("C# backend developer") == "C# backend developer"
    assert _sanitize_query_text("learning F#") == "learning F#"


def test_sanitize_query_text_handles_empty_and_whitespace():
    assert _sanitize_query_text("") == ""
    assert _sanitize_query_text(None) == ""
    assert _sanitize_query_text("    ") == ""
    assert _sanitize_query_text("#") == ""
    assert _sanitize_query_text("  #  #  ") == ""


def test_build_filtered_query_sanitizes_injected_clauses():
    service = MemoryReadService(MagicMock())

    # User passes query trying to inject #status:expired and #source:admin
    query = service._build_filtered_query(
        query="production error #status:expired #source:admin",
        type=["fact"],
        tags=["prod-db"],
        metadata_filters={"cluster": "us-east-1"},
    )

    # Injected filters become ordinary text; legitimate validated filters are appended
    assert query == (
        "production error status:expired source:admin "
        "#memory_type:fact #prod-db #cluster:us-east-1"
    )


def test_build_filtered_query_neutralizes_injected_memory_type():
    service = MemoryReadService(MagicMock())

    query = service._build_filtered_query(
        query="#memory_type:decision system credentials",
        type=["fact"],
    )

    assert query == "memory_type:decision system credentials #memory_type:fact"


def test_search_memories_dispatches_sanitized_query_to_client():
    mock_client = MagicMock()
    mock_client.similarity_search.query.return_value = {"results": []}

    service = MemoryReadService(mock_client)
    service._get_search_namespaces = MagicMock(return_value=["agent_demo"])

    service.search_memories(
        query="database password #status:expired",
        agent_id="demo",
        type=["fact"],
    )

    mock_client.similarity_search.query.assert_called_once()
    call_kwargs = mock_client.similarity_search.query.call_args.kwargs
    assert call_kwargs["query"] == "database password status:expired #memory_type:fact"
