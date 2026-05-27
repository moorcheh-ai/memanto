import pytest
from unittest.mock import MagicMock, patch
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from integrations.langgraph.memanto_manager import MemoryRegistry, MemoryType

def test_confidence_clamping():
    # Test that confidence is clamped between 0.0 and 1.0
    payload_high = {"content": "Test", "confidence": 1.5}
    payload_low = {"content": "Test", "confidence": -0.5}
    
    res_high = MemoryRegistry.validate(MemoryType.FACT.value, payload_high)
    res_low = MemoryRegistry.validate(MemoryType.FACT.value, payload_low)
    
    assert res_high.confidence == 1.0
    assert res_low.confidence == 0.0

@patch("integrations.langgraph.memanto_checkpointer.SdkClient")
def test_occ_conflict(mock_sdk):
    mock_instance = mock_sdk.return_value
    # Mock existing memory with version 10
    mock_instance.get_memories.return_value = [
        {"content": "{}", "metadata": {"thread_id": "t1", "version": 10}}
    ]
    
    checkpointer = MemantoCheckpointer(agent_id="test_agent", api_key="key")
    config = {"configurable": {"thread_id": "t1"}}
    
    # Attempt to put a checkpoint with version 5 (stale)
    with pytest.raises(RuntimeError, match="State conflict"):
        checkpointer.put(
            config=config,
            checkpoint={"id": "cp1"},
            metadata={"version": 5},
            new_versions={}
        )

@patch("integrations.langgraph.memanto_checkpointer.SdkClient")
def test_full_persistence_cycle(mock_sdk):
    mock_instance = mock_sdk.return_value
    mock_instance.get_memories.return_value = []
    
    checkpointer = MemantoCheckpointer(agent_id="test_agent", api_key="key")
    config = {"configurable": {"thread_id": "t1"}}
    
    # Save
    checkpointer.put(config, {"id": "cp1", "state": "val"}, {"version": 1}, {})
    
    # Mock the retrieval for the get_tuple call
    mock_instance.get_memories.return_value = [
        {"content": '{"id": "cp1", "state": "val"}', "metadata": {"thread_id": "t1", "version": 1}}
    ]
    
    result = checkpointer.get_tuple(config)
    assert result.checkpoint["state"] == "val"
