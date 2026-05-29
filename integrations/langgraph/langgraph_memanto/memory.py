"""MemantoStore: a LangGraph BaseStore backed by Memanto's semantic memory."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Iterator, Optional, Sequence, Tuple

from langgraph.store.base import BaseStore, GetOp, Item, ListOptions, PutOp, SearchOp, SearchResult
from memanto.cli.client.sdk_client import SdkClient


class MemantoStore(BaseStore):
    """A LangGraph store that persists items in a Memanto agent namespace.

    Each `Item` is mapped to a Memanto memory with the namespace encoded in
    the memory's tags and a special key prefix. The memory content is the
    JSON‑serialized item value.

    Note: This implementation provides basic get/put/delete support and uses
    Memanto's `remember` (for put) and `recall` (for get/search). For full
    semantic search capabilities, use the `recall` tool directly.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        auto_create: bool = True,
        pattern: str = "tool",
        session_duration_hours: Optional[int] = None,
    ):
        self._api_key = api_key or os.getenv("MOORCHEH_API_KEY")
        if not self._api_key:
            raise ValueError(
                "MOORCHEH_API_KEY must be provided or set in environment"
            )
        self._agent_id = (
            agent_id
            or os.getenv("MEMANTO_DEFAULT_AGENT_ID")
            or "langgraph-agent"
        )
        self._auto_create = auto_create
        self._pattern = pattern
        self._session_duration_hours = session_duration_hours

        self._client: Optional[SdkClient] = None
        self._session_token: Optional[str] = None

    async def _ensure_ready(self) -> None:
        """Lazily initialise the SDK client and activate a session."""
        if self._client is not None and self._session_token is not None:
            return

        from memanto.cli.client.sdk_client import SdkClient

        self._client = SdkClient(
            api_key=self._api_key,
            agent_id=self._agent_id,
            auto_create=self._auto_create,
            pattern=self._pattern,
        )
        # Activate a session
        session_data = self._client.activate_session(
            duration_hours=self._session_duration_hours
        )
        self._session_token = session_data.get("session_token")

        if not self._session_token:
            raise RuntimeError("Failed to activate Memanto session")

    def _namespace_to_tag(self, namespace: Tuple[str, ...]) -> str:
        return f"namespace:{'.'.join(namespace)}"

    def _key_to_memory_prefix(self, key: str) -> str:
        # Use the key as a tag to help retrieval
        return f"store_key:{key}"

    async def aget(self, namespace: Tuple[str, ...], key: str) -> Optional[Item]:
        """Retrieve a single item by namespace and key."""
        await self._ensure_ready()
        # Use Memanto's recall with a filter based on namespace+key
        # We search for a memory that has both tags
        results = self._client.recall(
            query=key,  # use the key itself as query for exact match
            filters={
                "tags": [self._namespace_to_tag(namespace), self._key_to_memory_prefix(key)]
            },
            limit=1,
        )
        memories = results.get("memories", [])
        if not memories:
            return None
        memory = memories[0]
        # The stored value is in the `memory` field as JSON
        import json

        try:
            value = json.loads(memory.get("memory", "{}"))
        except (json.JSONDecodeError, TypeError):
            value = memory.get("memory")
        return Item(
            namespace=namespace,
            key=key,
            value=value,
            created_at=memory.get("created_at"),
            updated_at=memory.get("updated_at"),
        )

    async def aput(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Optional[dict[str, Any]],
        index: Optional[Any] = None,
    ) -> None:
        """Store an item."""
        await self._ensure_ready()
        import json

        memory_content = json.dumps(value) if isinstance(value, dict) else str(value)
        tags = [self._namespace_to_tag(namespace), self._key_to_memory_prefix(key)]
        self._client.remember(
            memory=memory_content,
            memory_type="artifact",  # store as structured artifact
            tags=tags,
        )

    async def adelete(self, namespace: Tuple[str, ...], key: str) -> None:
        """Delete an item by namespace and key.

        Note: Memanto does not currently expose a delete-memory endpoint.
        This is a no-op until that API is available.
        """
        # Memanto API doesn't support deletion yet; we skip.
        pass

    async def asearch(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        options: Optional[ListOptions] = None,
    ) -> AsyncIterator[SearchResult]:
        """Search items within a namespace prefix."""
        await self._ensure_ready()
        tag_filter = [self._namespace_to_tag(namespace_prefix)]
        filters = {"tags": tag_filter}
        limit = options.filter.limit if options and options.filter else 10
        results = self._client.recall(
            query=query or "",
            filters=filters,
            limit=limit,
        )
        memories = results.get("memories", [])
        import json

        for mem in memories:
            # Extract namespace and key from tags
            ns = ()  # fallback
            k = mem.get("id", "unknown")
            for tag in mem.get("tags", []):
                if tag.startswith("namespace:"):
                    ns = tuple(tag[len("namespace:"):].split("."))
                elif tag.startswith("store_key:"):
                    k = tag[len("store_key:"):]
            try:
                value = json.loads(mem.get("memory", "{}"))
            except (json.JSONDecodeError, TypeError):
                value = mem.get("memory")
            item = Item(
                namespace=ns,
                key=k,
                value=value,
                created_at=mem.get("created_at"),
                updated_at=mem.get("updated_at"),
            )
            yield SearchResult(item=item, score=mem.get("score"))

    # ------------------------------------------------------------------
    # Synchronous wrappers for convenience (LangGraph sometimes uses sync)
    # ------------------------------------------------------------------
    def get(self, namespace: Tuple[str, ...], key: str) -> Optional[Item]:
        import asyncio

        return asyncio.run(self.aget(namespace, key))

    def put(
        self,
        namespace: Tuple[str, ...],
        key: str,
        value: Optional[dict[str, Any]],
        index: Optional[Any] = None,
    ) -> None:
        import asyncio

        asyncio.run(self.aput(namespace, key, value, index))

    def delete(self, namespace: Tuple[str, ...], key: str) -> None:
        import asyncio

        asyncio.run(self.adelete(namespace, key))

    def search(
        self,
        namespace_prefix: Tuple[str, ...],
        query: Optional[str] = None,
        options: Optional[ListOptions] = None,
    ) -> Iterator[SearchResult]:
        import asyncio

        # Since async generator, we need to collect
        async def _collect():
            results = []
            async for r in self.asearch(namespace_prefix, query, options):
                results.append(r)
            return results

        results = asyncio.run(_collect())
        return iter(results)

    # ------------------------------------------------------------------
    # Batch operations (LangGraph may call these)
    # ------------------------------------------------------------------
    async def abatch_get_ops(self, ops: Sequence[GetOp]) -> list[Optional[Item]]:
        return [await self.aget(op.namespace, op.key) for op in ops]

    async def abatch_put_ops(self, ops: Sequence[PutOp]) -> None:
        for op in ops:
            await self.aput(op.namespace, op.key, op.value, op.index)

    def batch_get_ops(self, ops: Sequence[GetOp]) -> list[Optional[Item]]:
        import asyncio

        return asyncio.run(self.abatch_get_ops(ops))

    def batch_put_ops(self, ops: Sequence[PutOp]) -> None:
        import asyncio

        asyncio.run(self.abatch_put_ops(ops))
