import pytest
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from memanto.cli.client.sdk_client import SdkClient
from langgraph.checkpoint.base import Checkpoint

def test_memanto_checkpointer_persistence():
    sdk_client = SdkClient()
    agent_id = "test_agent_persistence"
    checkpointer = MemantoCheckpointer(agent_id=agent_id, sdk_client=sdk_client)
    
    config = {"configurable": {"thread_id": "test_thread"}}
    checkpoint = Checkpoint(v=1, ts="2023-01-01T00:00:00Z", checkpoint={"test": "data"})
    
    # Test put
    checkpointer.put(config, checkpoint, metadata={})
    
    # Test get_tuple
    tuple_res = checkpointer.get_tuple(config)
    assert tuple_res is not None
    assert tuple_res.checkpoint["test"] == "data"

def test_type_safe_manager():
    from integrations.langgraph.memanto_manager import MemantoManager
    from pydantic import BaseModel
    
    class UserState(BaseModel):
        name: str
        age: int
        
    sdk_client = SdkClient()
    manager = MemantoManager[UserState](agent_id="test_manager_agent", sdk_client=sdk_client)
    
    state = UserState(name="Architect", age=40)
    manager.store_state("user_1", state)
    
    retrieved = manager.retrieve_state("user_1", UserState)
    assert retrieved.name == "Architect"
    assert retrieved.age == 40
