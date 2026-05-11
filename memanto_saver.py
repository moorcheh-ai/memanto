from typing import Any, Optional
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from memanto import SdkClient

class MemantoSaver(BaseCheckpointSaver):
    def __init__(self, api_key: str, agent_id: str):
        super().__init__()
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def get_tuple(self, config: RunnableConfig) -> Optional[Any]:
        thread_id = config["configurable"].get("thread_id")
        memory = self.client.recall(query=f"checkpoint_{thread_id}", agent_id=self.agent_id)
        return memory[0].get("data") if memory else None

    def put(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata) -> str:
        thread_id = config["configurable"].get("thread_id")
        self.client.remember(
            text=f"checkpoint_{thread_id}",
            agent_id=self.agent_id,
            metadata={"thread_id": thread_id, "checkpoint": checkpoint, "metadata": metadata}
        )
        return checkpoint["id"]
