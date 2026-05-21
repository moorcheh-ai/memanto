import time
from typing import Any, Dict, Optional
from memanto.cli.client.sdk_client import SdkClient
from .memanto_checkpoint import CheckpointState, MemantoOCCError

class MemantoStateManager:
    def __init__(self, agent_id: str):
        self.client = SdkClient()
        self.agent_id = agent_id

    def get_state(self, thread_id: str, checkpoint_id: str) -> Optional[CheckpointState]:
        key = f"checkpoint:{thread_id}:{checkpoint_id}"
        raw_payload = self.client.get_memory(self.agent_id, key)
        if not raw_payload:
            return None
        return CheckpointState(**raw_payload)

    def save_state(self, state: CheckpointState) -> bool:
        key = f"checkpoint:{state.thread_id}:{state.checkpoint_id}"
        
        current_state = self.get_state(state.thread_id, state.checkpoint_id)
        if current_state and current_state.version != state.version:
            raise MemantoOCCError(
                f"Conflict detected for {key}. Expected version {state.version}, found {current_state.version}"
            )

        state.version += 1
        state.metadata["updated_at"] = time.time()
        
        self.client.save_memory(
            self.agent_id, 
            key, 
            state.model_dump()
        )
        return True
