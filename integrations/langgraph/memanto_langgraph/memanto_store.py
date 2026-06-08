from typing import Any, Optional, List
from memanto.cli.client.sdk_client import SdkClient
from .schema import MemoryItem

class MemantoStore:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.client = SdkClient(api_key=api_key, base_url=base_url)

    def put(self, namespace: str, key: str, value: Any) -> None:
        """Stores a memory item in the Memanto store."""
        self.client.write_memory(
            namespace=namespace,
            key=key,
            value=value
        )

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieves a memory item from the Memanto store."""
        result = self.client.read_memory(namespace=namespace, key=key)
        return result if result else None

    def search(self, namespace: str, query: str, limit: int = 5) -> List[MemoryItem]:
        """Searches for relevant memories within a specific namespace."""
        results = self.client.search_memories(namespace=namespace, query=query, limit=limit)
        return [
            MemoryItem(
                content=item.get("content", ""),
                namespace=namespace,
                metadata=item.get("metadata", {}),
                memory_id=item.get("id")
            ) for item in results
        ]

    def delete(self, namespace: str, key: str) -> bool:
        """Removes a memory item from the store."""
        return self.client.delete_memory(namespace=namespace, key=key)
