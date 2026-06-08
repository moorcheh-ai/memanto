import asyncio
from typing import Any, Optional, Sequence
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from .schema import MemantoStoreConfig, MemantoMemoryItem

class MemantoStore(BaseStore):
    def __init__(self, config: MemantoStoreConfig):
        super().__init__()
        self.config = config
        self.client = SdkClient(api_key=config.api_key, base_url=config.base_url)

    def _resolve_namespace(self, namespace: tuple[str, ...]) -> str:
        return "/".join(namespace) if namespace else self.config.default_namespace

    async def get(
        self, 
        namespace: tuple[str, ...], 
        key: str
    ) -> Optional[MemantoMemoryItem]:
        ns = self._resolve_namespace(namespace)
        result = await self.client.read_memory(namespace=ns, key=key)
        if not result:
            return None
        return MemantoMemoryItem(
            key=key,
            value=result.get("value"),
            namespace=ns,
            metadata=result.get("metadata", {})
        )

    async def put(
        self, 
        namespace: tuple[str, ...], 
        key: str, 
        value: Any
    ) -> None:
        ns = self._resolve_namespace(namespace)
        await self.client.write_memory(
            namespace=ns, 
            key=key, 
            value=value
        )

    async def search(
        self, 
        namespace: tuple[str, ...], 
        query: str
    ) -> Sequence[MemantoMemoryItem]:
        ns = self._resolve_namespace(namespace)
        results = await self.client.query_memory(namespace=ns, query=query)
        
        return [
            MemantoMemoryItem(
                key=item.get("key"),
                value=item.get("value"),
                namespace=ns,
                metadata=item.get("metadata", {})
            )
            for item in results
        ]

    async def delete(self, namespace: tuple[str, ...], key: str) -> None:
        ns = self._resolve_namespace(namespace)
        await self.client.delete_memory(namespace=ns, key=key)
