import pytest
from integrations.langgraph import MemantoSaver, MemantoOCCError
from memanto.cli.client.sdk_client import SdkClient

def test_cross_thread_persistence():
    agent_id = "test_agent_cross_thread"
    client = SdkClient()
    saver = MemantoSaver(agent_id=agent_id)
    
    # Write to Thread A
    config_a = {"configurable": {"thread_id": "thread_a"}}
    checkpoint_a = {"id": "1", "data": "state_a"}
    saver.put(config_a, checkpoint_a, {}, None)
    
    # Assert it's in Memanto
    raw = client.get_memory(agent_id, "checkpoint:thread_a:1")
    assert raw is not None
    assert raw["checkpoint"]["data"] == "state_a"

def test_occ_collision():
    agent_id = "test_agent_occ"
    saver = MemantoSaver(agent_id=agent_id)
    
    config = {"configurable": {"thread_id": "occ_thread"}}
    checkpoint = {"id": "1", "data": "initial"}
    
    # First save
    saver.put(config, checkpoint, {}, None)
    
    # Simulate a stale state object with version 0 (should be 1 now)
    from integrations.langgraph.memanto_checkpoint import CheckpointState
    stale_state = CheckpointState(
        thread_id="occ_thread",
        checkpoint_id="1",
        checkpoint=checkpoint,
        version=0 
    )
    
    from integrations.langgraph.memanto_manager import MemantoStateManager
    manager = MemantoStateManager(agent_id)
    
    with pytest.raises(MemantoOCCError):
        manager.save_state(stale_state)
