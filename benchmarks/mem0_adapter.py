"""
Mem0 framework adapter for benchmarking.

Uses the mem0ai Python package.
Requires: MEM0_API_KEY environment variable.
"""

import os
from .base import MemoryAdapter, MemoryResult


class Mem0Adapter(MemoryAdapter):
    """Adapter for the Mem0 memory framework."""

    def __init__(self):
        self._client = None
        self._user_id = None

    @property
    def name(self) -> str:
        return "Mem0"

    def setup(self, user_id: str) -> None:
        api_key = os.environ.get("MEM0_API_KEY", "")
        if not api_key:
            raise ValueError("MEM0_API_KEY environment variable is required")
        from mem0 import MemoryClient
        self._client = MemoryClient(api_key=api_key)
        self._user_id = user_id

    def store(self, content: str, metadata: dict | None = None) -> MemoryResult:
        try:
            meta = metadata or {}
            result = self._client.add(content, user_id=self._user_id, metadata=meta)
            tokens = len(content.split()) * 2
            return MemoryResult(
                success=True,
                latency_ms=0,
                tokens_used=tokens,
                data=result,
            )
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error="Operation failed. See logs for details.")

    def retrieve(self, query: str, limit: int = 5) -> MemoryResult:
        try:
            result = self._client.search(query, user_id=self._user_id, limit=limit)
            memories = result if isinstance(result, list) else [result]
            total_tokens = sum(len(str(m).split()) * 2 for m in memories)
            return MemoryResult(
                success=True,
                latency_ms=0,
                tokens_used=total_tokens,
                data=memories,
            )
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error="Operation failed. See logs for details.")

    def update(self, memory_id: str, content: str) -> MemoryResult:
        try:
            result = self._client.update(memory_id, content)
            return MemoryResult(
                success=True,
                latency_ms=0,
                tokens_used=len(content.split()) * 2,
                data=result,
            )
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error="Operation failed. See logs for details.")

    def delete(self, memory_id: str) -> MemoryResult:
        try:
            result = self._client.delete(memory_id)
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error="Operation failed. See logs for details.")

    def get_all(self) -> MemoryResult:
        try:
            result = self._client.get_all(user_id=self._user_id)
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error="Operation failed. See logs for details.")

    def cleanup(self) -> None:
        try:
            self._client.delete_all(user_id=self._user_id)
        except Exception:
            pass
