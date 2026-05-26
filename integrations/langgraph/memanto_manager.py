from typing import TypeVar, Generic, List, Optional
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpoint import MemoryWrapper

T = TypeVar("T")

class MemoryManager(Generic[T]):
    def __init__(self, sdk_client: SdkClient, agent_id: str):
        self.client = sdk_client
        self.agent_id = agent_id
        self.valid_types = {
            "fact", "preference", "user_trait", "event", 
            "goal", "constraint", "observation", "belief", 
            "habit", "connection", "sentiment", "milestone", "context"
        }

    def store_memory(self, content: T, memory_type: str, metadata: dict = None) -> MemoryWrapper[T]:
        if memory_type not in self.valid_types:
            raise ValueError(f"Invalid memory type. Must be one of {self.valid_types}")
            
        wrapper = MemoryWrapper(
            content=content,
            memory_type=memory_type,
            metadata=metadata or {}
        )
        
        self.client.save_semantic_memory(
            agent_id=self.agent_id,
            memory_type=memory_type,
            content=wrapper.model_dump_json(),
            metadata=wrapper.metadata
        )
        return wrapper

    def recall_memories(self, query: str, memory_type: Optional[str] = None) -> List[MemoryWrapper[T]]:
        results = self.client.query_semantic_memories(
            agent_id=self.agent_id,
            query=query,
            memory_type=memory_type
        )
        
        return [MemoryWrapper.model_validate_json(res["content"]) for res in results]
