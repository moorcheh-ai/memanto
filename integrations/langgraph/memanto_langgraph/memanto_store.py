from typing import Any, Optional, Iterable
from pydantic import TypeAdapter
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from .schema import MemantoMemoryItem

class MemantoStore(BaseStore):
    """
    Memanto implementation of LangGraph BaseStore for long-term semantic memory.
    Moves state recovery from Checkpointers to persistent semantic storage.
    """
    def __init__(self, sdk_client: SdkClient):
        super().__init__()
        self.sdk_client = sdk_client

    def put(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        namespace_str = ":".join(namespace)
        # Use Pydantic to ensure the value is serializable via our schema
        item = MemantoMemoryItem(
            key=key,
            value=value,
            namespace=namespace_str
        )
        self.sdk_client.save_memory(
            agent_id=namespace_str,
            memory_key=item.key,
            content=str(item.value),
            metadata=item.metadata or {}
        )

    def get(self, namespace: tuple[str, ...], key: str) -> Optional[Any]:
        namespace_str = ":".join(namespace)
        memory = self.sdk_client.get_memory(
            agent_id=namespace_str,
            memory_key=key
        )
        if not memory:
            return None
        
        return memory.get("content")

    def search(self, namespace: tuple[str, ...], query: str) -> Iterable[Any]:
        namespace_str = ":".join(namespace)
        results = self.sdk_client.search_memories(
            agent_id=namespace_str,
            query=query
        )
        for res in results:
            yield res.get("content")

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        namespace_str = ":".join(namespace)
        self.sdk_client.delete_memory(
            agent_id=namespace_str,
            memory_key=key
        )
