"""
Memanto framework adapter for benchmarking.

Uses the memanto Python package with Moorcheh backend.
Requires: MOORCHEH_API_KEY environment variable.
"""

import os
from .base import MemoryAdapter, MemoryResult


class MemantoAdapter(MemoryAdapter):
    """Adapter for the Memanto memory framework (Moorcheh backend)."""

    def __init__(self):
        self._client = None
        self._user_id = None

    @property
    def name(self) -> str:
        return "Memanto"

    def setup(self, user_id: str) -> None:
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise ValueError("MOORCHEH_API_KEY environment variable is required")
        from memanto import Memanto
        self._client = Memanto(api_key=api_key, user_id=user_id)
        self._user_id = user_id

    def store(self, content: str, metadata: dict | None = None) -> MemoryResult:
        try:
            meta = metadata or {}
            result = self._client.add(content, metadata=meta)
            tokens = getattr(result, "tokens_used", len(content.split()) * 2)
            return MemoryResult(
                success=True,
                latency_ms=0,  # measured externally via timed_call
                tokens_used=tokens,
                data=result,
            )
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def retrieve(self, query: str, limit: int = 5) -> MemoryResult:
        try:
            result = self._client.search(query, limit=limit)
            memories = result if isinstance(result, list) else [result]
            total_tokens = sum(
                len(str(m).split()) * 2 for m in memories
            )
            return MemoryResult(
                success=True,
                latency_ms=0,
                tokens_used=total_tokens,
                data=memories,
            )
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

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
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def delete(self, memory_id: str) -> MemoryResult:
        try:
            result = self._client.delete(memory_id)
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def get_all(self) -> MemoryResult:
        try:
            result = self._client.get_all()
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def cleanup(self) -> None:
        try:
            self._client.delete_all()
        except Exception:
            pass
