import pytest
from unittest.mock import MagicMock
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointSaver
from integrations.langgraph.memanto_manager import MemoryManager
from integrations.langgraph.memanto_checkpoint import MemoryWrapper

@pytest.fixture
def mock_sdk():
    sdk = MagicMock(spec=SdkClient)
    sdk.get_session_state.return_value = {"version_id": 1, "state": {}}
    sdk.update_session_state.return_value = True
    return sdk

def test_occ_success(mock_sdk):
    saver = MemantoCheckpointSaver(mock_sdk, "test_agent")
    config = {"configurable": {"thread_id": "test_thread"}}
    
    result = saver.put(config, {"data": "val"}, {})
    assert result == config
    mock_sdk.update_session_state.assert_called_once()

def test_occ_retry_on_conflict(mock_sdk):
    # Simulate version mismatch first, then success
    mock_sdk.get_session_state.side_effect = [
        {"version_id": 2}, # Read 1
        {"version_id": 1}, # Read 2 (Retry)
    ]
    mock_sdk.update_session_state.side_effect = [False, True]
    
    saver = MemantoCheckpointSaver(mock_sdk, "test_agent")
    config = {"configurable": {"thread_id": "test_thread"}}
    
    result = saver.put(config, {"data": "val"}, {})
    assert result == config
    assert mock_sdk.update_session_state.call_count == 2

def test_memory_manager_type_validation(mock_sdk):
    manager = MemoryManager(mock_sdk, "test_agent")
    
    with pytest.raises(ValueError):
        manager.store_memory("Invalid", "non_existent_type")
        
    manager.store_memory("Valid", "preference")
    mock_sdk.save_semantic_memory.assert_called_once()

def test_memory_wrapper_serialization():
    wrapper = MemoryWrapper(content="Test", memory_type="fact")
    json_data = wrapper.model_dump_json()
    reconstructed = MemoryWrapper.model_validate_json(json_data)
    assert reconstructed.content == "Test"
