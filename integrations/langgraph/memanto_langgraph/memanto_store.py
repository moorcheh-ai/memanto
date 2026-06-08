from typing import Any, AsyncIterable, Generic, List, Optional, TypeVar
from pydantic import BaseModel

from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient

from .schema import MemantoStoreConfig, MemantoMemoryItem

T = TypeVar("T")

class MemantoStore(BaseStore, Generic[T]):
    """
    A type-safe LangGraph BaseStore implementation using Memanto.
    
    This provider abstracts Memanto SDK operations into the LangGraph store 
    interface, allowing for generic memory schemas via Python Generics.
    """

    def __init__(self, config: MemantoStoreConfig):
        """
        Initialize the MemantoStore with the provided configuration.
        
        Args:
            config: MemantoStoreConfig containing API credentials and settings.
        """
        self.config = config
        self.client = SdkClient(api_key=config.api_key, base_url=config.base_url)

    def put(self, namespace: str, key: str, value: Any) -> None:
        """
        Store a value in the specified namespace and key.
        
        Args:
            namespace: The memory namespace (e.g., 'users', 'sessions').
            key: The unique identifier for the memory item.
            value: The data to store.
        """
        self.client.write_memory(
            namespace=namespace,
            key=key,
            value=value
        )

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """
        Retrieve a value from the specified namespace and key.
        
        Args:
            namespace: The memory namespace.
            key: The unique identifier for the memory item.
            
        Returns:
            The retrieved value if found, otherwise None.
        """
        result = self.client.read_memory(namespace=namespace, key=key)
        return result.get("value") if result else None

    def search(self, namespace: str, query: str) -> List[Any]:
        """
        Search for memories within a namespace using a query string.
        
        Args:
            namespace: The memory namespace to search.
            query: The search query.
            
        Returns:
            A list of memory items matching the query.
        """
        results = self.client.query_memory(namespace=namespace, query=query)
        return [item.get("value") for item in results] if results else []

    def delete(self, namespace: str, key: str) -> None:
        """
        Delete a specific memory item from the store.
        
        Args:
            namespace: The memory namespace.
            key: The unique identifier for the memory item.
        """
        self.client.delete_memory(namespace=namespace, key=key)

    async def aput(self, namespace: str, key: str, value: Any) -> None:
        """Async implementation of put."""
        self.put(namespace, key, value)

    async def aget(self, namespace: str, key: str) -> Optional[Any]:
        """Async implementation of get."""
        return self.get(namespace, key)

    async def asearch(self, namespace: str, query: str) -> List[Any]:
        """Async implementation of search."""
        return self.search(namespace, query)

    async def adelete(self, namespace: str, key: str) -> None:
        """Async implementation of delete."""
        self.delete(namespace, key)
