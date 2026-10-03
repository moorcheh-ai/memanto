from unittest.mock import MagicMock, patch

import pytest
from langgraph.store.base import (
    GetOp,
    ListNamespacesOp,
    PutOp,
    SearchOp,
)
from langgraph_memanto.store import (
    MemantoStore,
    _agent_id_to_namespace,
    _namespace_to_agent_id,
)


@pytest.fixture
def mock_sdk_client():
    with patch("langgraph_memanto.store.SdkClient") as mock:
        yield mock


# -- Namespace isolation -------------------------------------------------------

# Pairs of DIFFERENT namespaces that the previous ``"_".join(namespace)``
# mapping collapsed onto a single Memanto agent.
COLLIDING_NAMESPACES = [
    (("my", "ns"), ("my_ns",)),
    (("a", "b", "c"), ("a_b", "c")),
    (("a-b",), ("a", "b")),
    (("",), ()),
]


@pytest.mark.parametrize("ns_a,ns_b", COLLIDING_NAMESPACES)
def test_distinct_namespaces_never_share_an_agent(mock_sdk_client, ns_a, ns_b):
    """Two different namespaces must never resolve to the same Memanto agent.

    An agent *is* the memory scope: if two namespaces share one, the first can
    recall and overwrite the second's memories.
    """
    store = MemantoStore(api_key="test_key")
    mock_sdk_client.return_value = MagicMock()

    _, agent_a = store._ensure_client(ns_a)
    _, agent_b = store._ensure_client(ns_b)

    assert agent_a != agent_b


def test_namespace_agent_id_round_trip():
    """Every namespace must survive a encode/decode round trip."""
    for namespace in [
        (),
        ("alice",),
        ("my_ns",),
        ("my", "ns"),
        ("a-b",),
        ("a", "b", "c"),
        ("",),
        ("a", ""),
        ("", "b"),
        ("équipe", "été"),
        ("with space", "and.dot"),
        ("x" * 80,),
    ]:
        assert _agent_id_to_namespace(_namespace_to_agent_id(namespace)) == namespace


def test_agent_ids_never_start_with_a_dash():
    """A leading ``-`` would be parsed as an option by the Memanto CLI."""
    for namespace in [
        (),
        ("-a",),
        ("", "-b"),
        ("-a", "-b"),
        ("a-b",),
        ("--",),
    ]:
        agent_id = _namespace_to_agent_id(namespace)
        assert not agent_id.split("langgraph_", 1)[1].startswith("-"), agent_id


def test_reserved_default_component_is_escaped():
    """``("default",)`` and ``()`` must not end up on the same agent."""
    empty = _namespace_to_agent_id(())
    reserved = _namespace_to_agent_id(("default",))

    assert empty == "langgraph_default"
    assert reserved != empty
    assert _agent_id_to_namespace(reserved) == ("default",)


def test_empty_component_round_trips():
    for namespace in [("",), ("a", ""), ("", "b"), ("", ""), ("a", "", "b")]:
        assert _agent_id_to_namespace(_namespace_to_agent_id(namespace)) == namespace


def test_legacy_ids_still_decode():
    """Ids written by the previous mapping keep their historical namespace."""
    assert _agent_id_to_namespace("langgraph_my_ns") == ("my", "ns")
    assert _agent_id_to_namespace("langgraph_alice") == ("alice",)
    assert _agent_id_to_namespace("langgraph_default") == ()
    assert _agent_id_to_namespace("unrelated_agent") is None


def test_namespace_ids_stay_within_memanto_charset():
    """Agent ids must satisfy the charset Memanto validates server-side."""
    import re as _re

    for namespace in [("my", "ns"), ("a-b",), ("équipe",), ("",)]:
        agent_id = _namespace_to_agent_id(namespace)
        assert _re.fullmatch(r"[A-Za-z0-9_-]+", agent_id), agent_id


def test_single_alphanumeric_namespace_keeps_its_historical_id():
    """Stores created before this fix stay reachable for plain namespaces."""
    assert _namespace_to_agent_id(("alice",)) == "langgraph_alice"
    assert _namespace_to_agent_id(()) == "langgraph_default"


def test_list_namespaces_round_trips_encoded_agents(mock_sdk_client):
    """list_namespaces must report encoded namespaces losslessly."""
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance
    client_instance.list_agents.return_value = [
        {"agent_id": _namespace_to_agent_id(("my_ns",))},
        {"agent_id": _namespace_to_agent_id(("my", "ns"))},
        {"agent_id": "langgraph_alice"},
        {"agent_id": "unrelated_agent"},
    ]

    namespaces = store._do_list_namespaces(ListNamespacesOp())

    assert ("my_ns",) in namespaces
    assert ("my", "ns") in namespaces
    assert ("alice",) in namespaces
    assert len(namespaces) == 3


def test_list_namespaces_still_reports_legacy_agents(mock_sdk_client):
    """Agents written by the previous lossy mapping stay listable."""
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance
    client_instance.list_agents.return_value = [{"agent_id": "langgraph_my_ns"}]

    assert store._do_list_namespaces(ListNamespacesOp()) == [("my", "ns")]


def test_memanto_store_init():
    store = MemantoStore(api_key="test_key")
    assert store.api_key == "test_key"
    assert store._client_pool == {}


def test_ensure_client_creates_and_activates(mock_sdk_client):
    store = MemantoStore(api_key="test_key")

    # Mock the instance returned by SdkClient
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    namespace = ("test", "ns")
    client, agent_id = store._ensure_client(namespace)

    assert agent_id == "langgraph_test-ns"
    assert client == client_instance

    mock_sdk_client.assert_called_once_with(api_key="test_key")
    client_instance.create_agent.assert_called_once_with(
        agent_id="langgraph_test-ns", pattern="tool"
    )
    client_instance.activate_agent.assert_called_once_with(agent_id="langgraph_test-ns")

    # Second call should return cached client
    client2, agent_id2 = store._ensure_client(namespace)
    assert client2 == client
    assert mock_sdk_client.call_count == 1  # No new client created


def test_ensure_client_empty_namespace(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client, agent_id = store._ensure_client(())
    assert agent_id == "langgraph_default"


def test_do_get_recent_success(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    # Mock recall_recent to return the expected memory
    client_instance.recall_recent.return_value = {
        "memories": [
            {
                "id": "mem-123",
                "tags": ["lg:key:my_key"],
                "type": "fact",
                "title": "my_key",
                "content": "some content",
                "confidence": 0.8,
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
            }
        ]
    }

    # Also need to mock _memory_to_item if we are relying on its internal format,
    # but let's see what _do_get returns. It returns an Item.
    op = GetOp(namespace=("my_ns",), key="my_key")
    item = store._do_get(op)

    assert item is not None
    assert item.key == "my_key"
    assert item.namespace == ("my_ns",)
    assert item.value["content"] == "some content"
    assert item.value["kind"] == "fact"

    client_instance.recall_recent.assert_called_once_with(
        agent_id="langgraph_my_5fns", limit=100
    )


def test_do_get_recovers_key_from_comma_separated_tags(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall_recent.return_value = {
        "memories": [
            {
                "id": "mem-123",
                "tags": "lg:key:my_key,urgent",
                "type": "fact",
                "title": "my_key",
                "content": "some content",
                "confidence": 0.8,
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
            }
        ]
    }

    op = GetOp(namespace=("my_ns",), key="my_key")
    item = store._do_get(op)

    assert item is not None
    assert item.key == "my_key"
    assert item.value["tags"] == ["urgent"]


def test_do_get_fallback_success(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    # Mock recall_recent to return empty
    client_instance.recall_recent.return_value = {"memories": []}

    # Mock recall to return the expected memory
    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-123",
                "tags": ["lg:key:my_key"],
                "type": "fact",
                "title": "my_key",
                "content": "fallback content",
                "confidence": 0.8,
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-01T00:00:00Z",
            }
        ]
    }

    op = GetOp(namespace=("my_ns",), key="my_key")
    item = store._do_get(op)

    assert item is not None
    assert item.value["content"] == "fallback content"
    client_instance.recall.assert_called_once_with(
        agent_id="langgraph_my_5fns", query="my_key", limit=100, tags=["lg:key:my_key"]
    )


def test_do_get_not_found(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall_recent.return_value = {"memories": []}
    client_instance.recall.return_value = {"memories": []}

    op = GetOp(namespace=("my_ns",), key="my_key")
    item = store._do_get(op)

    assert item is None


def test_do_put_success(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance
    client_instance.recall_recent.return_value = {"memories": []}
    client_instance.recall.return_value = {"memories": []}

    op = PutOp(
        namespace=("my_ns",),
        key="my_key",
        value={"kind": "fact", "content": "my new fact", "title": "fact title"},
    )
    store._do_put(op)

    client_instance.remember.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        memory_type="fact",
        title="fact title",
        content="my new fact",
        confidence=0.8,
        tags=["lg:key:my_key"],
        source="langgraph-store",
        provenance="explicit_statement",
    )


def test_do_put_escapes_commas_in_key_tags(mock_sdk_client):
    """LangGraph keys may contain commas; tags are comma-serialized downstream."""
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    op = PutOp(namespace=("my_ns",), key="thread,checkpoint", value={"content": "c"})
    store._do_put(op)

    client_instance.remember.assert_called_once()
    assert client_instance.remember.call_args.kwargs["tags"] == [
        "lg:key:v1:thread%2Ccheckpoint"
    ]


def test_tags_to_key_unescapes_encoded_key_tags():
    assert MemantoStore._tags_to_key(["lg:key:v1:thread%2Ccheckpoint"]) == (
        "thread,checkpoint"
    )


def test_do_put_upsert_behavior(mock_sdk_client):
    """LangGraph put acts as an upsert, preserves existing types, and fails safe."""
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    # 1. Test update
    client_instance.recall_recent.return_value = {
        "memories": [{"id": "mem-1", "tags": ["lg:key:my_key"], "type": "fact"}]
    }
    store._do_put(PutOp(namespace=("my_ns",), key="my_key", value={"content": "new"}))
    client_instance.update_memory.assert_called_once()
    assert "type" not in client_instance.update_memory.call_args.kwargs["updates"]
    client_instance.remember.assert_not_called()

    # 2. Test failure safe
    client_instance.reset_mock()
    client_instance.recall_recent.return_value = {"memories": []}
    client_instance.recall.side_effect = RuntimeError("backend down")
    import pytest

    with pytest.raises(RuntimeError, match="Cannot safely determine"):
        store._do_put(PutOp(namespace=("my_ns",), key="my_key", value={"content": "x"}))
    client_instance.update_memory.assert_not_called()
    client_instance.remember.assert_not_called()


def test_do_put_stringifies_non_string_content(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    op = PutOp(namespace=("my_ns",), key="answer", value={"content": 42})
    store._do_put(op)

    client_instance.remember.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        memory_type=None,
        title="42",
        content="42",
        confidence=0.8,
        tags=["lg:key:answer"],
        source="langgraph-store",
        provenance="explicit_statement",
    )


def test_do_put_delete_not_supported(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    op = PutOp(namespace=("my_ns",), key="my_key", value=None)

    with pytest.raises(
        NotImplementedError, match="MemantoStore does not support delete"
    ):
        store._do_put(op)


def test_do_search_recent(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall_recent.return_value = {
        "memories": [
            {
                "id": "mem-123",
                "tags": ["lg:key:key1"],
                "type": "fact",
                "title": "key1",
                "content": "some content",
            }
        ]
    }

    op = SearchOp(namespace_prefix=("my_ns",), query=None)
    items = store._do_search(op)

    assert len(items) == 1
    assert items[0].key == "key1"
    client_instance.recall_recent.assert_called_once_with(
        agent_id="langgraph_my_5fns", limit=100, type=None
    )


def test_do_search_wildcard_with_tags_uses_backend_tag_filter(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-789",
                "tags": ["lg:key:key3", "project:apollo"],
                "type": "fact",
                "title": "key3",
                "content": "older tagged memory",
            }
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",),
        query="*",
        filter={"tags": ["project:apollo"]},
    )
    items = store._do_search(op)

    assert len(items) == 1
    assert items[0].key == "key3"
    client_instance.recall_recent.assert_not_called()
    client_instance.recall.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        query="*",
        limit=10,
        type=None,
        tags=["project:apollo"],
        min_similarity=None,
    )


def test_do_search_semantic(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-456",
                "tags": ["lg:key:key2"],
                "type": "observation",
                "content": "observed",
            }
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",), query="test query", filter={"type": "observation"}
    )
    items = store._do_search(op)

    assert len(items) == 1
    assert items[0].key == "key2"
    client_instance.recall.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        query="test query",
        limit=10,
        type=["observation"],
        tags=None,
        min_similarity=None,
    )


def test_do_search_filters_min_confidence_without_changing_similarity(
    mock_sdk_client,
):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-high",
                "tags": ["lg:key:key-high"],
                "type": "fact",
                "content": "high confidence",
                "confidence": 0.95,
            },
            {
                "id": "mem-low",
                "tags": ["lg:key:key-low"],
                "type": "fact",
                "content": "low confidence",
                "confidence": 0.4,
            },
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",),
        query="test query",
        filter={"min_confidence": 0.9, "min_similarity": 0.2},
        limit=10,
    )
    items = store._do_search(op)

    assert [item.key for item in items] == ["key-high"]
    client_instance.recall.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        query="test query",
        limit=store._MEMANTO_RECALL_CAP,
        type=None,
        tags=None,
        min_similarity=0.2,
    )


def test_do_search_min_confidence_zero_keeps_legacy_memories(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall_recent.return_value = {
        "memories": [
            {
                "id": "legacy-memory",
                "tags": ["lg:key:legacy"],
                "type": "fact",
                "content": "stored before confidence existed",
            }
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",),
        query="*",
        filter={"min_confidence": 0.0},
        limit=10,
    )
    items = store._do_search(op)

    assert [item.key for item in items] == ["legacy"]


def test_do_search_accepts_string_tag_filter(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-456",
                "tags": ["lg:key:key2", "urgent"],
                "type": "observation",
                "content": "observed",
            }
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",), query="test query", filter={"tags": "urgent"}
    )
    items = store._do_search(op)

    assert len(items) == 1
    assert items[0].key == "key2"
    client_instance.recall.assert_called_once_with(
        agent_id="langgraph_my_5fns",
        query="test query",
        limit=10,
        type=None,
        tags=["urgent"],
        min_similarity=None,
    )


def test_do_search_recovers_key_from_comma_separated_tags(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall.return_value = {
        "memories": [
            {
                "id": "mem-456",
                "tags": "lg:key:key2,urgent",
                "type": "observation",
                "content": "observed",
            }
        ]
    }

    op = SearchOp(
        namespace_prefix=("my_ns",), query="test query", filter={"tags": ["urgent"]}
    )
    items = store._do_search(op)

    assert len(items) == 1
    assert items[0].key == "key2"
    assert items[0].value["tags"] == ["urgent"]


def test_batch_execution(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.recall_recent.return_value = {"memories": []}
    client_instance.recall.return_value = {"memories": []}

    ops = [
        PutOp(namespace=("ns",), key="key", value={"content": "c"}),
        GetOp(namespace=("ns",), key="key"),
    ]

    results = store.batch(ops)
    assert len(results) == 2
    assert results[0] is None
    assert results[1] is None
    assert client_instance.remember.call_count == 1


def test_do_list_namespaces(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    # Mock list_agents returning various agents
    client_instance.list_agents.return_value = [
        {"agent_id": "langgraph_default"},
        {"agent_id": "langgraph_my_ns"},
        {"agent_id": "langgraph_other_ns_sub"},
        {"agent_id": "unrelated_agent"},
    ]

    op = ListNamespacesOp()
    namespaces = store._do_list_namespaces(op)

    # Should ignore unrelated_agent, and parse the rest
    assert () in namespaces
    assert ("my", "ns") in namespaces
    assert ("other", "ns", "sub") in namespaces
    assert len(namespaces) == 3


def test_do_list_namespaces_match_conditions(mock_sdk_client):
    store = MemantoStore(api_key="test_key")
    client_instance = MagicMock()
    mock_sdk_client.return_value = client_instance

    client_instance.list_agents.return_value = [
        {"agent_id": "langgraph_my_ns"},
        {"agent_id": "langgraph_my_other"},
        {"agent_id": "langgraph_not_my"},
    ]

    from langgraph.store.base import MatchCondition

    # Match prefix
    op = ListNamespacesOp(
        match_conditions=[MatchCondition(match_type="prefix", path=("my",))]
    )
    namespaces = store._do_list_namespaces(op)
    assert namespaces == [("my", "ns"), ("my", "other")]
