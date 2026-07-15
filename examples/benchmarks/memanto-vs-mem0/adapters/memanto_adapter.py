"""
Memanto adapter for the benchmark harness.

Uses:
    memanto.cli.client.sdk_client.SdkClient
    create_agent → activate_agent → remember (batch) → recall → deactivate_agent
"""

from __future__ import annotations

import logging
import os
import uuid as _uuid

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

from .base import IngestResult, MemoryAdapter, RecallResult

logger = logging.getLogger(__name__)


class MemantoAdapter(MemoryAdapter):
    """
    Memanto memory adapter.

    Environment variables:
        MOORCHEH_API_KEY  (required)

    Each benchmark run uses an agent_id scoped to the user_id so that
    multiple runs don't pollute each other.
    """

    name = "Memanto"

    def __init__(self, api_key: str | None = None) -> None:
        _key = (api_key or os.environ.get("MOORCHEH_API_KEY", "")).strip()
        if not _key:
            raise ValueError("MOORCHEH_API_KEY is required for MemantoAdapter")
        self._sdk = SdkClient(api_key=_key)
        self._agent_id: str | None = None

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def setup(self, user_id: str) -> None:
        self._agent_id = f"bench-{user_id}-{_uuid.uuid4().hex[:8]}"
        try:
            self._sdk.create_agent(
                agent_id=self._agent_id,
                pattern="tool",
                description=f"Benchmark agent for user {user_id}",
            )
        except AgentAlreadyExistsError:
            logger.debug("Agent '%s' already exists — reusing", self._agent_id)
        except Exception as exc:
            logger.warning("create_agent warning: %s", exc)

        self._sdk.activate_agent(self._agent_id, duration_hours=2)
        logger.debug("Memanto session active for '%s'", self._agent_id)

    def teardown(self, user_id: str) -> None:
        if self._agent_id:
            try:
                self._sdk.deactivate_agent(self._agent_id)
            except Exception as exc:
                logger.warning("deactivate_agent warning: %s", exc)

    # -----------------------------------------------------------------------
    # Ingest
    # -----------------------------------------------------------------------

    def ingest_session(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict],
    ) -> IngestResult:
        """Store each user message as a typed memory."""
        raw_text = self.messages_to_text(messages)
        tokens_in = self.count_tokens(raw_text)

        # Build batch payload — one memory per user turn
        user_turns = [m for m in messages if m["role"] == "user"]
        memories_payload = [
            {
                "content": m["content"],
                "type": None,  # let Memanto's auto-parser classify
                "title": f"{session_id} turn",
                "tags": [f"session:{session_id}", "benchmark"],
                "confidence": 0.9,
                "source": "benchmark",
            }
            for m in user_turns
        ]

        def _store():
            try:
                return self._sdk.batch_remember(
                    agent_id=self._agent_id,
                    memories=memories_payload,
                )
            except Exception:
                # Fall back to individual stores if batch fails
                results = []
                for mem in memories_payload:
                    r = self._sdk.remember(
                        agent_id=self._agent_id,
                        memory_type=mem["type"],
                        title=mem["title"],
                        content=mem["content"],
                        confidence=mem["confidence"],
                        tags=mem["tags"],
                        source=mem["source"],
                    )
                    results.append(r)
                return results

        raw, elapsed = self.timed(_store)
        return IngestResult(
            system=self.name,
            session_id=session_id,
            latency_s=elapsed,
            tokens_ingested=tokens_in,
            raw_response=raw,
        )

    # -----------------------------------------------------------------------
    # Recall
    # -----------------------------------------------------------------------

    def recall(
        self,
        user_id: str,
        query_id: str,
        query: str,
    ) -> RecallResult:
        """Semantic recall from Memanto."""

        def _recall():
            return self._sdk.recall(
                agent_id=self._agent_id,
                query=query,
                limit=10,
            )

        raw, elapsed = self.timed(_recall)

        memories: list[dict] = raw.get("memories", [])
        memory_texts = [m.get("content", "") for m in memories]

        # Build answer by concatenating the top recalled memories
        answer = "\n".join(memory_texts) if memory_texts else "(no memories recalled)"

        # Token count = query tokens + all returned memory tokens
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
