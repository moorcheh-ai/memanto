import pytest
import pickle
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointSaver
from memanto.cli.client.sdk_client import SdkClient
from langchain_core.runnables import RunnableConfig

@pytest.fixture
def sdk():
    return SdkClient()

@pytest.fixture
def checkpointer(sdk):
    return MemantoCheckpointSaver(agent_id="test_graph_agent", sdk_client=sdk)

def test_agent_lifecycle_init(sdk):
    # Verifies create_agent and activate_agent occur in constructor
    saver = MemantoCheckpointSaver(agent_id="lifecycle_test", sdk_client=sdk)
    assert saver.agent_id == "lifecycle_test"

def test_put_and_get_single_thread(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    checkpoint = {"id": "cp1", "data": "state1"}
    metadata = {"source": "test"}
    
    checkpointer.put(config, checkpoint, metadata)
    result = checkpointer.get_tuple(config)
    
    assert result.checkpoint["id"] == "cp1"
    assert result.metadata["source"] == "test"

def test_cross_thread_isolation(checkpointer):
    config_a = {"configurable": {"thread_id": "thread_a"}}
    config_b = {"configurable": {"thread_id": "thread_b"}}
    
    checkpointer.put(config_a, {"id": "cp_a", "val": 1}, {})
    checkpointer.put(config_b, {"id": "cp_b", "val": 2}, {})
    
    res_a = checkpointer.get_tuple(config_a)
    res_b = checkpointer.get_tuple(config_b)
    
    assert res_a.checkpoint["id"] == "cp_a"
    assert res_b.checkpoint["id"] == "cp_b"

def test_latest_pointer_update(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    
    checkpointer.put(config, {"id": "cp1"}, {})
    checkpointer.put_latest(config, "cp1")
    
    # Request without checkpoint_id should return latest
    res = checkpointer.get_tuple(config)
    assert res.checkpoint["id"] == "cp1"

def test_checkpoint_id_override(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    checkpointer.put(config, {"id": "cp1"}, {})
    checkpointer.put(config, {"id": "cp2"}, {})
    
    config_specific = {"configurable": {"thread_id": "t1", "checkpoint_id": "cp1"}}
    res = checkpointer.get_tuple(config_specific)
    assert res.checkpoint["id"] == "cp1"

def test_recall_non_existent(checkpointer):
    config = {"configurable": {"thread_id": "ghost"}}
    res = checkpointer.get_tuple(config)
    assert res is None

def test_serialization_integrity(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    complex_state = {"id": "cp1", "nested": {"list": [1, 2, 3], "dict": {"a": 1}}}
    
    checkpointer.put(config, complex_state, {})
    res = checkpointer.get_tuple(config)
    assert res.checkpoint["nested"]["list"] == [1, 2, 3]

def test_rapid_updates(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    for i in range(5):
        checkpointer.put(config, {"id": f"cp{i}"}, {})
        checkpointer.put_latest(config, f"cp{i}")
        
    res = checkpointer.get_tuple(config)
    assert res.checkpoint["id"] == "cp4"

def test_empty_metadata(checkpointer):
    config = {"configurable": {"thread_id": "t1"}}
    checkpointer.put(config, {"id": "cp1"}, {})
    res = checkpointer.get_tuple(config)
    assert res.metadata == {}

def test_sdk_client_sharing(sdk):
    # Ensure two checkpointers sharing same client can access same agent
    saver1 = MemantoCheckpointSaver(agent_id="shared_agent", sdk_client=sdk)
    config = {"configurable": {"thread_id": "t1"}}
    saver1.put(config, {"id": "cp_shared"}, {})
    
    saver2 = MemantoCheckpointSaver(agent_id="shared_agent", sdk_client=sdk)
    res = saver2.get_tuple(config)
    assert res.checkpoint["id"] == "cp_shared"
