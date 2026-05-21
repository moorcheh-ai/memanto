import json
from typing import Any, Dict, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from memanto.cli.client.sdk_client import SdkClient

class MemantoCheckpointer(BaseCheckpointSaver):
    def __init__(self, sdk_client: SdkClient, agent_id: str):
        super().__init__()
        self.sdk = sdk_client
        self.agent_id = agent_id

    def put(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: CheckpointMetadata) -> Dict[str, Any]:
        thread_id = config["configurable"].get("thread_id")
        checkpoint_id = checkpoint["id"]
        
        payload = {
            "checkpoint": checkpoint,
            "metadata": metadata
        }
        
        storage_key = f"checkpoint_{thread_id}_{checkpoint_id}"
        self.sdk.store(
            agent_id=self.agent_id,
            key=storage_key,
            value=json.dumps(payload)
        )
        
        # Update the latest pointer for the thread
        self.sdk.store(
            agent_id=self.agent_id,
            key=f"latest_{thread_id}",
            value=checkpoint_id
        )
        
        return config

    def get(self, config: Dict[str, Any]) -> Optional[Checkpoint]:
        thread_id = config["configurable"].get("thread_id")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        
        if not checkpoint_id:
            checkpoint_id = self.sdk.recall(
                agent_id=self.agent_id, 
                key=f"latest_{thread_id}"
            )
            
        if not checkpoint_id:
            return None
            
        storage_key = f"checkpoint_{thread_id}_{checkpoint_id}"
        raw_value = self.sdk.recall(
            agent_id=self.agent_id, 
            key=storage_key
        )
        
        if not raw_value:
            return None
            
        payload = json.loads(raw_value)
        return payload["checkpoint"]

    def list(self, config: Dict[str, Any], filter: Optional[Dict[str, Any]] = None):
        # Memanto SDK currently optimizes for key-value retrieval; 
        # implementation depends on SDK support for prefix searching.
        return []
