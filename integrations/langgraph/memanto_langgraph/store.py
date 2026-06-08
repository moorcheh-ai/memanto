from typing import Any, AsyncIterator, Generic, TypeVar, Optional
from pydantic import BaseModel

from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient

from .schema import MemantoStoreItem, T

class MemantoStore(BaseStore, Generic[T]):
    """
    Adapter implementing LangGraph's BaseStore using Memanto SDK.
    This allows Memanto to serve as a first-class persistence layer.
    """

    def __init__(self, sdk_client: SdkClient, item_type: type[T]):
        super().__init__()
        self._client = sdk_client
        self._item_type = item_type

    def put(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        """
        Stores a value in Memanto under a specific namespace and key.
        """
        namespace_path = "/".join(namespace)
        
        # Wrap value in type-safe Pydantic model
        store_item = MemantoStoreItem[T](value=value)
        
        # SDK call to write memory
        self._client.write(
            namespace=namespace_path,
            key=key,
            content=store_item.model_dump_json()
        )

    def get(self, namespace: tuple[str, ...], key: str) -> Optional[Any]:
        """
        Retrieves a value from Memanto.
        """
        namespace_path = "/".join(namespace)
        raw_content = self._client.read(namespace=namespace_path, key=key)
        
        if not raw_content:
            return None
            
        # Deserialize and return the inner value of the Generic T
        item = MemantoStoreItem[T].model_validate_json(raw_content)
        return item.value

    def search(self, namespace: tuple[str, ...], query: str) -> AsyncIterator[tuple[str, Any]]:
        """
        Performs a semantic search across the specified namespace.
        
        Complexity:
        - Time: O(log N) where N is the number of memories in the namespace (Vector index lookup).
        - Space: O(K) where K is the number of returned results.
        """
        namespace_path = "/".join(namespace)
        search_results = self._client.search(
            namespace=namespace_path,
            query=query
        )

        for result in search_results:
            # Result expected as (key, content)
            key, content = result
            item = MemantoStoreItem[T].model_validate_json(content)
            yield (key, item.value)

    async def aget(self, namespace: tuple[str, ...], key: str) -> Optional[Any]:
        return self.get(namespace, key)

    async def aput(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        self.put(namespace, key, value)

    async def asearch(self, namespace: tuple[str, ...], query: str) -> AsyncIterator[tuple[str, Any]]:
        async for item in self.search(namespace, query):
            yield item
