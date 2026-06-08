import asyncio
from typing import Any, Optional, List
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from .schema import MemantoStoreConfig

class MemantoStore(BaseStore):
    def __init__(self, config: MemantoStoreConfig):
        super().__init__()
        self.config = config
        self._client = SdkClient(
            api_key=config.api_key, 
            base_url=config.base_url
        )

    async def put(self, namespace: str, key: str, value: Any) -> None:
        await self._client.write_memory(
            namespace=namespace,
            key=key,
            value=value
        )

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        memory_record = await self._client.read_memory(
            namespace=namespace, 
            key=key
        )
        return memory_record.get("value") if memory_record else None

    async def search(self, namespace: str, query: str) -> List[Any]:
        search_results = await self._client.query_memory(
            namespace=namespace, 
            query=query
        )
        return [item.get("value") for item in search_results] if search_results else []

    async def delete(self, namespace: str, key: str) -> None:
        await self._client.delete_memory(
            namespace=namespace, 
            key=key
        )
