import json
from typing import Any, Dict, Optional, Iterator
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointTuple, CheckpointMetadata
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_manager import MemoryType

class MemantoCheckpointer(BaseCheckpointSaver):
    def __init__(self, agent_id: str, api_key: str):
        super().__init__()
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def put(
        self, 
        config: Dict[str, Any], 
        checkpoint: Checkpoint, 
        metadata: CheckpointMetadata, 
        new_versions: Dict[str, Any]
    ) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        
        # Optimistic Concurrency Control: Check current version before write
        existing = self.get_tuple(config)
        current_version = 0
        if existing:
            current_version = existing.checkpoint.get("version", 0)

        if current_version > metadata.get("version", 0):
            raise RuntimeError(f"State conflict: Current version {current_version} exceeds provided version.")

        serialized_state = json.dumps(checkpoint)
        
        # Use SESSION_CONTEXT for LangGraph state persistence
        self.client.put_memory(
            agent_id=self.agent_id,
            memory_type=MemoryType.SESSION_CONTEXT.value,
            content=serialized_state,
            metadata={
                "thread_id": thread_id,
                "version": metadata.get("version", current_version + 1),
                "checkpoint_id": checkpoint.get("id")
            }
        )
        
        return {
            "checkpoint_id": checkpoint.get("id"),
            "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", "")
        }

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        memories = self.client.get_memories(
            agent_id=self.agent_id,
            memory_type=MemoryType.SESSION_CONTEXT.value
        )
        
        # Filter for the specific thread_id
        thread_memories = [m for m in memories if m.get("metadata", {}).get("thread_id") == thread_id]
        if not thread_memories:
            return None
            
        # Get the most recent version
        latest = max(thread_memories, key=lambda x: x.get("metadata", {}).get("version", 0))
        
        checkpoint = json.loads(latest["content"])
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=latest.get("metadata", {}),
            parent_config=None # Simplified for persistence bridge
        )

    def list(
        self, 
        config: Optional[Dict[str, Any]], 
        *, 
        filter: Optional[Dict[str, Any]] = None, 
        before: Optional[Dict[str, Any]] = None, 
        limit: Optional[int] = None
    ) -> Iterator[CheckpointTuple]:
        # Implementation for listing history of states
        thread_id = config["configurable"]["thread_id"] if config else None
        memories = self.client.get_memories(
            agent_id=self.agent_id,
            memory_type=MemoryType.SESSION_CONTEXT.value
        )
        
        filtered = [m for m in memories if not thread_id or m.get("metadata", {}).get("thread_id") == thread_id]
        for m in filtered[-limit:] if limit else filtered:
            yield CheckpointTuple(
                config=config,
                checkpoint=json.loads(m["content"]),
                metadata=m.get("metadata", {}),
                parent_config=None
            )
