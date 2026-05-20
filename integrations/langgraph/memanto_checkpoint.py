import json
import time
from typing import Any, Dict, Optional, Sequence
from pydantic import BaseModel, Field
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from memanto.cli.client.sdk_client import SdkClient

class CheckpointSchema(BaseModel):
    checkpoint: Dict[str, Any]
    metadata: Dict[str, Any]
    version: int = Field(default=1)
    timestamp: float = Field(default_factory=time.time)

class MemantoCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, sdk_client: SdkClient, namespace_prefix: str = "lg_checkpoint"):
        super().__init__()
        self.client = sdk_client
        self.prefix = namespace_prefix

    def _get_namespace(self, thread_id: str) -> str:
        return f"{self.prefix}_{thread_id}"

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        namespace = self._get_namespace(thread_id)
        checkpoint_id = checkpoint["id"]
        
        current_record = self.client.get_memory(namespace=namespace, key=checkpoint_id)
        version = 1
        if current_record:
            try:
                existing_data = json.loads(current_record.get("value", "{}"))
                version = existing_data.get("version", 0) + 1
            except (json.JSONDecodeError, AttributeError):
                pass

        payload = CheckpointSchema(
            checkpoint=checkpoint,
            metadata=metadata,
            version=version
        ).model_dump_json()

        self.client.save_memory(
            namespace=namespace,
            key=checkpoint_id,
            value=payload
        )
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        namespace = self._get_namespace(thread_id)

        if not checkpoint_id:
            memories = self.client.list_memories(namespace=namespace)
            if not memories:
                return None
            
            sorted_mems = sorted(
                memories, 
                key=lambda x: x.get("timestamp", 0), 
                reverse=True
            )
            checkpoint_id = sorted_mems[0].get("key")

        record = self.client.get_memory(namespace=namespace, key=checkpoint_id)
        if not record:
            return None

        parsed = CheckpointSchema.model_validate_json(record["value"])
        
        return CheckpointTuple(
            config=config,
            checkpoint=parsed.checkpoint,
            metadata=parsed.metadata,
            parent_config=parsed.metadata.get("parent_config")
        )

    def list(
        self,
        config: Dict[str, Any],
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Sequence[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        namespace = self._get_namespace(thread_id)
        
        memories = self.client.list_memories(namespace=namespace)
        results = []
        
        for mem in memories:
            checkpoint_id = mem["key"]
            record = self.client.get_memory(namespace=namespace, key=checkpoint_id)
            parsed = CheckpointSchema.model_validate_json(record["value"])
            results.append(CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}},
                checkpoint=parsed.checkpoint,
                metadata=parsed.metadata,
                parent_config=parsed.metadata.get("parent_config")
            ))
            
        return results
