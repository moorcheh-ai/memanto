import pickle
from typing import Any, Dict, Optional, Sequence
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple
from memanto.cli.client.sdk_client import SdkClient

class MemantoCheckpointer(BaseCheckpointSaver):
    def __init__(self, agent_id: str, sdk_client: Optional[SdkClient] = None):
        super().__init__()
        self.agent_id = agent_id
        self.client = sdk_client or SdkClient()

    def put(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: Dict[str, Any]) -> Dict[str, Any]:
        # Serialize checkpoint to bytes for storage in Memanto
        checkpoint_bytes = pickle.dumps(checkpoint)
        checkpoint_id = config["configurable"].get("thread_id", "default")
        
        storage_key = f"checkpoint_{checkpoint_id}"
        self.client.write_memory(
            namespace=self.agent_id,
            key=storage_key,
            value=checkpoint_bytes.hex() 
        )
        return config

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        checkpoint_id = config["configurable"].get("thread_id", "default")
        storage_key = f"checkpoint_{checkpoint_id}"
        
        raw_val = self.client.read_memory(namespace=self.agent_id, key=storage_key)
        if not raw_val:
            return None
            
        checkpoint = pickle.loads(bytes.fromhex(raw_val))
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata={},
            parent_config=None
        )

    def list(self, config: Dict[str, Any], *, filter: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> Sequence[CheckpointTuple]:
        # Basic implementation for listing; usually filtered by thread_id
        return []
