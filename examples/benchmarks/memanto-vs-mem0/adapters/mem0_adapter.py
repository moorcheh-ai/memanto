"""
Mem0 adapter for the benchmark harness.

Uses the Mem0 Platform API (hosted):
    MemoryClient(api_key=)
    .add(messages, user_id=)   → ingest
    .search(query, filters=)   → recall

Environment variables:
    MEM0_API_KEY  (required) — get one free at https://app.mem0.ai
"""

from __future__ import annotations

import logging
import os

from .base import IngestResult, MemoryAdapter, RecallResult

logger = logging.getLogger(__name__)


class Mem0Adapter(MemoryAdapter):
    """
    Mem0 Platform memory adapter.

    Mem0 handles memory extraction automatically — you pass the full
    conversation and it decides what to store. This is the most
    representative comparison: same raw input, different memory systems.

    Environment variables:
        MEM0_API_KEY  (required)
    """

    name = "Mem0"

    def __init__(self, api_key: str | None = None) -> None:
        _key = (api_key or os.environ.get("MEM0_API_KEY", "")).strip()
        if not _key:
            raise ValueError("MEM0_API_KEY is required for Mem0Adapter")
        # Lazy import so the benchmark can import this file even if mem0ai
        # is not installed (it will fail at runtime when used, not at import).
        from mem0 import MemoryClient  # type: ignore[import]

        self._client = MemoryClient(api_key=_key)
        self._user_id: str | None = None

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def setup(self, user_id: str) -> None:
        """Mem0 is stateless — no per-run setup needed."""
        self._user_id = f"bench-{user_id}"
        logger.debug("Mem0 ready for user '%s'", self._user_id)

    def teardown(self, user_id: str) -> None:
        """Delete all memories for this benchmark user to keep runs clean."""
        try:
            self._client.delete_all(user_id=self._user_id)
            logger.debug("Mem0: deleted all memories for '%s'", self._user_id)
        except Exception as exc:
            logger.warning("Mem0 teardown warning: %s", exc)

    # -----------------------------------------------------------------------
    # Ingest
    # -----------------------------------------------------------------------

    def ingest_session(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict],
    ) -> IngestResult:
        """
        Pass the full conversation to Mem0 for automatic extraction.

        Mem0's .add() sends the messages to an LLM that extracts and
        deduplicates memories — we measure total tokens in and wall time.
        Note: Mem0 Platform processes memories asynchronously (returns PENDING).
        The harness waits for indexing before running recall.
        """
        raw_text = self.messages_to_text(messages)
        tokens_in = self.count_tokens(raw_text)

        def _ingest():
            return self._client.add(
                messages,
                user_id=self._user_id,
                metadata={"session_id": session_id},
            )

        raw, elapsed = self.timed(_ingest)
        return IngestResult(
            system=self.name,
            session_id=session_id,
            latency_s=elapsed,
            tokens_ingested=tokens_in,
            raw_response=raw,
        )

    def wait_for_indexing(self, timeout_s: int = 30, poll_interval_s: int = 3) -> int:
        """
        Poll Mem0 until at least one memory is indexed for this user.
        Returns the number of memories found, or 0 on timeout.
        """
        import time as _time

        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            try:
                all_mems = self._client.get_all(filters={"user_id": self._user_id})
                if isinstance(all_mems, dict):
                    items = all_mems.get("results", [])
                elif isinstance(all_mems, list):
                    items = all_mems
                else:
                    items = []
                count = len(items)
                if count > 0:
                    return count
            except Exception:
                pass
            _time.sleep(poll_interval_s)
        return 0

    # -----------------------------------------------------------------------
    # Recall
    # -----------------------------------------------------------------------

    def recall(
        self,
        user_id: str,
        query_id: str,
        query: str,
    ) -> RecallResult:
        """Semantic search via Mem0 .search()."""

        def _search():
            return self._client.search(
                query,
                filters={"user_id": self._user_id},
                limit=10,
            )

        raw, elapsed = self.timed(_search)

        # Mem0 returns {"results": [{"memory": str, "score": float, ...}]}
        results = raw.get("results", []) if isinstance(raw, dict) else raw
        memory_texts = [r.get("memory", "") for r in results]
        answer = "\n".join(memory_texts) if memory_texts else "(no memories recalled)"

        tokens_used = self.count_tokens(query) + sum(
            self.count_tokens(t) for t in memory_texts
        )

        return RecallResult(
            system=self.name,
            query_id=query_id,
            query=query,
            answer=answer,
            latency_s=elapsed,
            tokens_used=tokens_used,
            memories_returned=memory_texts,
            raw_response=raw,
        )
