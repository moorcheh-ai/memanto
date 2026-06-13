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
        """Initialise the Memanto adapter with empty client and user ID."""
        self._client = None
        self._user_id = None

    def _ensure_setup(self) -> None:
        """Raise RuntimeError if setup() was not called.

        Raises:
            RuntimeError: If the client has not been initialised via setup().
        """
        if self._client is None:
            raise RuntimeError(
                f"{self.name} adapter: setup() must be called before operations"
            )

    @property
    def name(self) -> str:
        """Return the display name of this adapter.

        Returns:
            str: The string "Memanto".
        """
        return "Memanto"

    def setup(self, user_id: str) -> None:
        """Configure the adapter with a user ID and initialise the Memanto client.

        Args:
            user_id: The user identifier to associate memories with.

        Raises:
            ValueError: If the MOORCHEH_API_KEY environment variable is not set.
        """
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise ValueError("MOORCHEH_API_KEY environment variable is required")
        from memanto import Memanto
        self._client = Memanto(api_key=api_key, user_id=user_id)
        self._user_id = user_id

    def store(self, content: str, metadata: dict | None = None) -> MemoryResult:
        """Store a memory entry via the Memanto API.

        Args:
            content: The text content to store.
            metadata: Optional metadata dictionary to attach to the memory.

        Returns:
            MemoryResult: Result indicating success or failure, with token count.
        """
        self._ensure_setup()
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
        """Search for memories matching a query via the Memanto API.

        Args:
            query: The search query string.
            limit: Maximum number of results to return. Defaults to 5.

        Returns:
            MemoryResult: Result containing a list of matching memories.
        """
        self._ensure_setup()
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
        """Update an existing memory entry by ID.

        Args:
            memory_id: The identifier of the memory to update.
            content: The new text content.

        Returns:
            MemoryResult: Result indicating success or failure.
        """
        self._ensure_setup()
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
        """Delete a memory entry by ID.

        Args:
            memory_id: The identifier of the memory to delete.

        Returns:
            MemoryResult: Result indicating success or failure.
        """
        self._ensure_setup()
        try:
            result = self._client.delete(memory_id)
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def get_all(self) -> MemoryResult:
        """Retrieve all memories for the current user.

        Returns:
            MemoryResult: Result containing all stored memories.
        """
        self._ensure_setup()
        try:
            result = self._client.get_all()
            return MemoryResult(success=True, latency_ms=0, data=result)
        except Exception as e:
            return MemoryResult(success=False, latency_ms=0, error=str(e))

    def cleanup(self) -> None:
        """Delete all memories for the current user.

        Logs a warning if cleanup fails instead of silently ignoring.
        """
        self._ensure_setup()
        try:
            self._client.delete_all()
        except Exception as e:
            import logging
            logging.warning(f"Cleanup failed: {e}")
