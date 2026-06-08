from typing import Any, Dict, List, Optional, Tuple
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from .schema import MemoryPayload

class MemantoStore(BaseStore):
    """
    LangGraph BaseStore implementation for Memanto.
    Maps LangGraph store operations to Memanto SDK calls for long-term semantic memory.
    """
    def __init__(self, sdk_client: SdkClient):
        self.client = sdk_client

    def put(self, namespace: Tuple[str, ...], key: str, value: Any) -> None:
        # Extract agent_id from namespace for Memanto identification
        agent_id = namespace[0] if namespace else "default_agent"
        
        # Convert value to MemoryPayload for SDK compatibility
        payload = value if isinstance(value, dict) else {"content": value}
        
        # SDK call handles idempotency via internal versioning/last-write-wins
        self.client.create_memory(
            agent_id=agent_id,
            memory_key=key,
            content=payload
        )

    def get(self, namespace: Tuple[str, ...], key: str) -> Optional[Any]:
        agent_id = namespace[0] if namespace else "default_agent"
        memory = self.client.get_memory(agent_id=agent_id, memory_key=key)
        return memory.content if memory else None

    def search(self, namespace: Tuple[str, ...], query: str, limit: int = 10) -> List[Any]:
        agent_id = namespace[0] if namespace else "default_agent"
        results = self.client.search_memories(
            agent_id=agent_id,
            query=query,
            limit=limit
        )
        return [res.content for res in results]
