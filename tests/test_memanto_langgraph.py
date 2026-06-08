import pytest
from unittest.mock import MagicMock
from integrations.langgraph.memanto_langgraph import MemantoStore

@pytest.fixture
def mock_sdk():
    return MagicMock()

@pytest.fixture
def store(mock_sdk):
    return MemantoStore(sdk_client=mock_sdk)

def test_store_put(store, mock_sdk):
    namespace = ("user_1", "global")
    key = "pref"
    value = {"color": "blue"}
    
    store.put(namespace, key, value)
    
    mock_sdk.create_memory.assert_called_once_with(
        agent_id="user_1",
        memory_key=key,
        content=value
    )

def test_store_get(store, mock_sdk):
    mock_mem = MagicMock()
    mock_mem.content = "stored_value"
    mock_sdk.get_memory.return_value = mock_mem
    
    val = store.get(("user_1",), "pref")
    
    assert val == "stored_value"
    mock_sdk.get_memory.assert_called_with(agent_id="user_1", memory_key="pref")

def test_store_search(store, mock_sdk):
    mock_res1 = MagicMock()
    mock_res1.content = "fact 1"
    mock_res2 = MagicMock()
    mock_res2.content = "fact 2"
    mock_sdk.search_memories.return_value = [mock_res1, mock_res2]
    
    results = store.search(("user_1",), "query")
    
    assert results == ["fact 1", "fact 2"]
    mock_sdk.search_memories.assert_called_with(
        agent_id="user_1", 
        query="query", 
        limit=10
    )
