import time
import logging
from typing import Any, Optional, Dict
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpoint import GraphState

logger = logging.getLogger("memanto_checkpointer")

class MemantoCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, sdk_client: SdkClient, agent_id: str):
        super().__init__()
        self.client = sdk_client
        self.agent_id = agent_id

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return None
            
        checkpoint_data = self.client.get_session_state(
            agent_id=self.agent_id, 
            session_id=thread_id
        )
        
        if not checkpoint_data:
            return None
            
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint_data,
            metadata={},
            parent_config=None
        )

    def put(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = config["configurable"].get("thread_id")
        
        max_retries = 3
        backoff = 0.5
        
        for attempt in range(max_retries):
            current_state = self.client.get_session_state(
                agent_id=self.agent_id, 
                session_id=thread_id
            )
            
            current_version = current_state.get("version_id", 0) if current_state else 0
            
            if current_state and current_state.get("version_id") != current_version:
                time.sleep(backoff * (2 ** attempt))
                continue
                
            checkpoint_payload = {
                **checkpoint,
                "version_id": current_version + 1,
                "updated_at": time.time()
            }
            
            success = self.client.update_session_state(
                agent_id=self.agent_id,
                session_id=thread_id,
                state=checkpoint_payload,
                expected_version=current_version
            )
            
            if success:
                return config
                
        raise RuntimeError(f"OCC failure: Concurrent update conflict for thread {thread_id}")

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        return self.get_tuple(config)

    async def aput(self, config: Dict[str, Any], checkpoint: Checkpoint, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return self.put(config, checkpoint, metadata)
