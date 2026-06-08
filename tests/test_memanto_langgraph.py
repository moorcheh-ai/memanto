import pytest
from unittest.mock import MagicMock
from integrations.langgraph.memanto_langgraph import MemantoStore
from memanto.cli.client.sdk_client import SdkClient

def test_memanto_store_put_get():
    mock_sdk = MagicMock(spec=SdkClient)
    # Mock read to return a JSON string matching MemantoStoreItem schema
    mock_sdk.read.return_value = '{"value": "Dark Mode", "metadata": {}}'
    
    store = MemantoStore[str](sdk_client=mock_sdk, item_type=str)
    namespace = ("test", "user")
    key = "pref"
    value = "Dark Mode"
    
    store.put(namespace, key, value)
    
    # Verify SDK write was called with JSON
    mock_sdk.write.assert_called_once()
    args, kwargs = mock_sdk.write.call_args
    assert '"value":"Dark Mode"' in kwargs['content']
    
    # Verify retrieval
    result = store.get(namespace, key)
    assert result == "Dark Mode"

def test_memanto_store_type_safety():
    mock_sdk = MagicMock(spec=SdkClient)
    mock_sdk.read.return_value = '{"value": 42, "metadata": {}}'
    
    store = MemantoStore[int](sdk_client=mock_sdk, item_type=int)
    result = store.get(("test",), "age")
    
    assert isinstance(result, int)
    assert result == 42
