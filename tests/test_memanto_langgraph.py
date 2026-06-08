import pytest
import asyncio
from integrations.langgraph.memanto_langgraph import MemantoStore, MemantoStoreConfig

@pytest.mark.asyncio
async def test_store_lifecycle():
    config = MemantoStoreConfig(api_key="test_key")
    store = MemantoStore(config)
    
    namespace = "test_ns"
    key = "test_key"
    val = {"foo": "bar"}
    
    await store.put(namespace, key, val)
    result = await store.get(namespace, key)
    assert result == val
    
    await store.delete(namespace, key)
    result_after_delete = await store.get(namespace, key)
    assert result_after_delete is None
