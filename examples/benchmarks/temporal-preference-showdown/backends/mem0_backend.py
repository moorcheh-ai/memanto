"""
Mem0 Backend — uses the real Mem0 cloud API.

Mem0 stores raw conversation turns and uses its own LLM-based compression
and retrieval. This gives us genuine production numbers for comparison.

Requires: MEM0_API_KEY environment variable.
"""
from __future__ import annotations

import logging
import os
import time

from mem0 import MemoryClient

from .base import BackendStats, count_tokens

logger = logging.getLogger(__name__)


class Mem0Backend:
    name = "Mem0 (cloud)"
    # Mem0 processes memories asynchronously; allow time for indexing before queries.
    index_wait_s = 10

    def __init__(self) -> None:
        api_key = os.environ.get("MEM0_API_KEY")
        if not api_key:
            raise EnvironmentError("MEM0_API_KEY is not set")
        self._client = MemoryClient(api_key=api_key)
        self.stats = BackendStats()

    def add(self, messages: list[dict], user_id: str) -> None:
        """Store a conversation session in Mem0."""
        text_blob = " ".join(m["content"] for m in messages)
        tokens = count_tokens(text_blob)

        t0 = time.perf_counter()
        self._client.add(messages, user_id=user_id)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.stats.record_ingest(tokens, elapsed_ms)

    def search(self, query: str, user_id: str) -> str:
        """Retrieve relevant memories for a query."""
        t0 = time.perf_counter()
        results = self._client.search(query, filters={"user_id": user_id}, limit=5)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        memories = results if isinstance(results, list) else results.get("results", [])
        retrieved_text = " ".join(
            m.get("memory", m.get("text", "")) for m in memories
        )
        tokens = count_tokens(retrieved_text)
        self.stats.record_retrieve(tokens, elapsed_ms)
        return retrieved_text

    def reset(self, user_id: str) -> None:
        """Delete all memories for a user (clean slate between runs)."""
        try:
            self._client.delete_all(user_id=user_id)
        except Exception as exc:
            logger.warning(
                "Mem0 delete_all failed for %s: %s — stale memories may affect results",
                user_id, exc,
            )
