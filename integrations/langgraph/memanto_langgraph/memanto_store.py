from typing import Any, Dict, Optional, List, Iterable
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.schema import MemantoMemoryItem, MemantoStoreConfig

class MemantoStore(BaseStore):
    """
    Type-safe LangGraph BaseStore implementation for Memanto.
    Provides cross-thread semantic memory persistence.
    """
    def __init__(self, config: MemantoStoreConfig):
        self.config = config
        self.client = SdkClient(api_key=config.api_key, base_url=config.base_url)

    def put(self, namespace: str, key: str, value: Any) -> None:
        # Map LangGraph store put to Memanto SDK write operation
        # Ensure AGENT_ID consistency is handled via namespace
        item = MemantoMemoryItem(
            namespace=namespace,
            key=key,
            value=value
        )
        self.client.write_memory(
            namespace=item.namespace,
            key=item.key,
            value=item.value,
            metadata=item.metadata
        )

    def get(self, namespace: str, key: str) -> Optional[Any]:
        # Map LangGraph store get to Memanto SDK read operation
        response = self.client.read_memory(namespace=namespace, key=key)
        return response.get("value") if response else None

    def search(self, namespace: str, query: str, limit: int = 10) -> Iterable[Any]:
        # Map LangGraph semantic search to Memanto SDK query
        results = self.client.query_memory(
            namespace=namespace, 
            query=query, 
            limit=limit
        )
        for result in results:
            yield result.get("value")

    def delete(self, namespace: str, key: str) -> None:
        self.client.delete_memory(namespace=namespace, key=key)
