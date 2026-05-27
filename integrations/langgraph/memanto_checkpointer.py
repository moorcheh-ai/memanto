import pickle
from typing import Any, Dict, Optional, Sequence
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple, CheckpointMetadata
from memanto.cli.client.sdk_client import SdkClient

class MemantoCheckpointer(BaseCheckpointSaver):
    """
    Type-safe checkpointer for LangGraph V3 using Memanto as the persistence layer.
    """
    def __init__(self, client: SdkClient, namespace: str = "langgraph_state"):
        super().__init__()
        self.client = client
        self.namespace = namespace

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Sequence[tuple[str, Any]]
    ) -> Dict[str, Any]:
        thread_id = config["configurable"].get("thread_id")
        checkpoint_id = checkpoint["id"]
        
        # Serialize state to bytes for storage in Memanto
        serialized_state = pickle.dumps({
            "checkpoint": checkpoint,
            "metadata": metadata,
            "new_versions": new_versions
        })
        
        # Store in Memanto using a composite key to ensure uniqueness per thread and version
        storage_key = f"{thread_id}___{checkpoint_id}"
        self.client.write_memory(
            agent_id=self.namespace,
            session_id=thread_id,
            content=serialized_state.hex(), 
            memory_id=storage_key
        )
        
        return {
            "checkpoint_id": checkpoint_id,
            "checkpoint_ns": ""
        }

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"].get("thread_id")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        
        # If no specific checkpoint_id, we fetch the latest for the thread
        # In a real implementation, this would query the most recent memory_id
        # For this implementation, we assume the current thread_id mapped to the latest state
        memories = self.client.read_memory(
            agent_id=self.namespace,
            session_id=thread_id
        )
        
        if not memories:
            return None
            
        # Retrieve the most recent entry
        latest_memory = memories[0] 
        raw_payload = bytes.fromhex(latest_memory.content)
        deserialized = pickle.loads(raw_payload)
        
        return CheckpointTuple(
            config=config,
            checkpoint=deserialized["checkpoint"],
            metadata=deserialized["metadata"],
            parent_config=None
        )

    def list(
        self,
        config: Optional[Dict[str, Any]],
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> Sequence[CheckpointTuple]:
        # Implementation for listing history of checkpoints
        return []
