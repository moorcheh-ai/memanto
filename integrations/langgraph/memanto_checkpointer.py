import json
from typing import Any, Dict, Optional, List
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple
from memanto.cli.client.sdk_client import SdkClient

class MemantoCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, api_key: str, agent_id: str):
        super().__init__()
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: Dict[str, Any],
        new_versions: Any,
    ) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_payload = {
            "checkpoint": checkpoint,
            "metadata": metadata,
            "versions": new_versions
        }
        
        # We use the Memanto SDK to store the state as a high-priority memory object 
        # linked to the thread_id namespace
        storage_key = f"checkpoint:{thread_id}"
        content = json.dumps(checkpoint_payload)
        
        # store using the SDK's remember functionality specifically for state persistence
        self.client.remember(self.agent_id, f"{storage_key} | {content}")
        
        return config

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        storage_key = f"checkpoint:{thread_id}"
        
        memories = self.client.recall(self.agent_id, query=storage_key)
        if not memories:
            return None
            
        # Extract the payload from the stored string
        raw_content = memories[0]["content"].split(" | ", 1)[1]
        payload = json.loads(raw_content)
        
        return CheckpointTuple(
            config=config,
            checkpoint=payload["checkpoint"],
            metadata=payload["metadata"],
            parent_config=None # Simplified for PoC
        )

    def list(
        self,
        config: Optional[Dict[str, Any]],
        filter: Optional[Dict[str, Any]],
    ) -> Any:
        # Simplified implementation for persistence proof
        return []
