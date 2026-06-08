import pytest
from unittest.mock import MagicMock
from integrations.langgraph.memanto_langgraph import MemantoStore
from memanto.cli.client.sdk_client import SdkClient

@pytest.fixture
def mock_sdk():
    return MagicMock(spec=SdkClient)

@pytest.fixture
def store(mock_sdk):
    return MemantoStore(sdk_client=mock_sdk)

def test_store_put(store, mock_sdk):
    namespace = ("test", "user")
    key = "pref"
    val = "blue"
    
    store.put(namespace, key, val)
    
    mock_sdk.save_memory.assert_called_once_with(
        agent_id="test:user",
        memory_key=key,
        content=val,
        metadata={}
    )

def test_store_get(store, mock_sdk):
    mock_sdk.get_memory.return_value = {"content": "blue"}
    
    val = store.get(("test", "user"), "pref")
    
    assert val == "blue"
    mock_sdk.get_memory.assert_called_once_with(
        agent_id="test:user",
        memory_key="pref"
    )

def test_store_search(store, mock_sdk):
    mock_sdk.search_memories.return_value = [{"content": "result1"}, {"content": "result2"}]
    
    results = list(store.search(("test", "user"), "query"))
    
    assert results == ["result1", "result2"]
    mock_sdk.search_memories.assert_called_once_with(
        agent_id="test:user",
        query="query"
    )

def test_store_delete(store, mock_sdk):
    store.delete(("test", "user"), "pref")
    
    mock_sdk.delete_memory.assert_called_once_with(
        agent_id="test:user",
        memory_key="pref"
    )
