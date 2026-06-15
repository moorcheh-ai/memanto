from unittest.mock import MagicMock, patch

import pytest
from langgraph.store.base import (
    GetOp,
    ListNamespacesOp,
    PutOp,
    SearchOp,
)
from langgraph_memanto.store import MemantoStore


@pytest.fixture
def mock_sdk_client():
    with patch("langgraph_memanto.store.SdkClient") as mock:
        yield mock


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

    assert agent_id == "langgraph_test_ns"
    assert client == client_instance

    mock_sdk_client.assert_called_once_with(api_key="test_key")
    client_instance.create_agent.assert_called_once_with(
        agent_id="langgraph_test_ns", pattern="tool"
    )
    client_instance.activate_agent.assert_called_once_with(agent_id="langgraph_test_ns")

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
        agent_id="langgraph_my_ns", limit=100
    )


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
        agent_id="langgraph_my_ns", query="my_key", limit=100, tags=["lg:key:my_key"]
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

    op = PutOp(
        namespace=("my_ns",),
        key="my_key",
        value={"kind": "fact", "content": "my new fact", "title": "fact title"},
    )
    store._do_put(op)

    client_instance.remember.assert_called_once_with(
        agent_id="langgraph_my_ns",
        memory_type="fact",
        title="fact title",
        content="my new fact",
        confidence=0.8,
        tags=["lg:key:my_key"],
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
        agent_id="langgraph_my_ns", limit=100, type=None
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
        agent_id="langgraph_my_ns",
        query="test query",
        limit=10,
        type=["observation"],
        tags=None,
        min_similarity=None,
    )


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
