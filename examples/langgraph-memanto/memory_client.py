"""
Memanto client wrapper for the LangGraph example.

Wraps the Memanto SDK client with a simpler interface that LangGraph
nodes can call without worrying about session management or agent lifecycle.
"""

import logging
import os
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

# Default agent ID for this example
DEFAULT_AGENT_ID = "langgraph-research-assistant"


class MemantoMemory:
    """
    Lightweight wrapper around Memanto's SdkClient.

    Handles agent creation/activation so LangGraph nodes only need to call
    remember(), recall(), and answer() — no session ceremony.

    Usage:
        memory = MemantoMemory(api_key="...")
        memory.remember("fact", "LLMs scale with data", "Research finding...")
        results = memory.recall("What do we know about LLM scaling?")
        answer = memory.answer("Explain the scaling hypothesis")
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ):
        api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required. "
                "Set it in your .env file or pass it to MemantoMemory()."
            )

        self.agent_id = agent_id
        self._client = SdkClient(api_key=api_key)
        self._ensure_agent()

    def _ensure_agent(self) -> None:
        """Create the agent if it doesn't exist, then activate it."""
        try:
            self._client.get_agent(self.agent_id)
        except Exception:
            logger.info("Creating Memanto agent '%s' ...", self.agent_id)
            self._client.create_agent(self.agent_id)

        self._client.activate_agent(self.agent_id)
        logger.info("Memanto agent '%s' ready", self.agent_id)

    @property
    def client(self) -> SdkClient:
        """Expose the underlying SDK client for advanced use."""
        return self._client

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Store a memory in Memanto.

        Args:
            memory_type: One of ``fact``, ``preference``, ``goal``, ``decision``,
                ``artifact``, ``learning``, ``event``, ``instruction``,
                ``relationship``, ``context``, ``observation``, ``commitment``,
                ``error``.
            title: Short title (max 100 chars).
            content: Full memory content.
            confidence: Confidence score 0.0–1.0.
            tags: Optional tags for filtering.

        Returns:
            Dict with ``memory_id``, ``status``, etc.
        """
        return self._client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
        )

    def batch_remember(
        self, memories: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Store multiple memories at once."""
        return self._client.batch_remember(
            agent_id=self.agent_id,
            memories=[
                {
                    "type": m["type"],
                    "title": m["title"],
                    "content": m["content"],
                    "confidence": m.get("confidence", 0.8),
                    "tags": m.get("tags", []),
                    "source": m.get("source", "user"),
                }
                for m in memories
            ],
        )

    def recall(
        self,
        query: str,
        limit: int = 10,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search memories by semantic similarity.

        Args:
            query: Natural-language query.
            limit: Max results.
            min_confidence: Minimum confidence filter (0.0–1.0).

        Returns:
            List of matching memory dicts.
        """
        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            min_confidence=min_confidence,
        )
        return result.get("memories", [])

    def answer(
        self,
        question: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Answer a question using RAG over stored memories.

        Args:
            question: Natural-language question.
            limit: Number of memories to use as context.

        Returns:
            Dict with ``answer`` (str) and ``sources`` (list).
        """
        return self._client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=limit,
        )
