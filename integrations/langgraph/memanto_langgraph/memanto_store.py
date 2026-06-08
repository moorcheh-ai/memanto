from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient

class MemoryItem(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MemantoStore(BaseStore):
    def __init__(self, sdk_client: SdkClient):
        super().__init__()
        self.client = sdk_client

    def put(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        # Map LangGraph tuple namespace to a single Memanto namespace string
        memanto_namespace = ":".join(namespace)
        
        # Ensure value is formatted for Memanto SDK
        content = value if isinstance(value, str) else str(value)
        
        self.client.create_memory(
            agent_id=memanto_namespace,
            content=content,
            metadata={"key": key}
        )

    def get(self, namespace: tuple[str, ...], key: str) -> Optional[Any]:
        memanto_namespace = ":".join(namespace)
        memories = self.client.search_memories(
            agent_id=memanto_namespace,
            query=key,
            limit=1
        )
        
        if not memories:
            return None
            
        # Return the content of the most relevant match
        return memories[0].content

    def search(self, namespace: tuple[str, ...], query: str, limit: int = 10) -> List[Any]:
        memanto_namespace = ":".join(namespace)
        results = self.client.search_memories(
            agent_id=memanto_namespace,
            query=query,
            limit=limit
        )
        return [res.content for res in results]
