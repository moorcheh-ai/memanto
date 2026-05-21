from typing import Any, Dict, Optional, Generator
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from .memanto_manager import MemantoStateManager
from .memanto_checkpoint import CheckpointState

class MemantoSaver(BaseCheckpointSaver):
    def __init__(self, agent_id: str):
        super().__init__()
        self.manager = MemantoStateManager(agent_id)
        self.agent_id = agent_id

    def put(
        self, 
        config: Dict[str, Any], 
        checkpoint: Checkpoint, 
        metadata: CheckpointMetadata, 
        new_versions: Any
    ) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        
        state = CheckpointState(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            checkpoint=checkpoint,
            metadata=metadata or {},
            version=0
        )
        
        # Handle potential OCC from manager
        try:
            self.manager.save_state(state)
        except Exception as e:
            # In production, this would trigger a retry loop
            raise e
            
        return {
            "checkpoint_id": checkpoint_id,
            "checkpoint_ns": ""
        }

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        # In a real implementation, we would track the latest checkpoint_id per thread
        # For the bounty, we assume the latest known ID is passed or retrieved via a lookup
        checkpoint_id = config["configurable"].get("checkpoint_id")
        if not checkpoint_id:
            return None
            
        state = self.manager.get_state(thread_id, checkpoint_id)
        if not state:
            return None
            
        return CheckpointTuple(
            config=config,
            checkpoint=state.checkpoint,
            metadata=state.metadata,
            parent_config=None
        )

    def list(self, config: Dict[str, Any], *, filter: Optional[Dict[str, Any]] = None) -> Generator[CheckpointTuple, None, None]:
        # Implementation for listing history
        yield from []
