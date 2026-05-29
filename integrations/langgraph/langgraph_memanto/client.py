"""Memanto client wrapper for LangGraph integration."""

import os
from typing import Optional

from memanto.cli.client.sdk_client import SdkClient


class MemantoClient:
    """Thin wrapper around the Memanto SDK client for use in LangGraph nodes.

    Handles automatic agent creation/session activation, and exposes
    the core memory operations as simple methods.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: str = "langgraph-default",
        agent_pattern: str = "tool",
        agent_auto_create: bool = True,
        session_duration_hours: int = 6,
    ):
        self._api_key = api_key or os.environ.get("MOORCHEH_API_KEY")
        if not self._api_key:
            raise ValueError(
                "MOORCHEH_API_KEY must be provided or set in environment"
            )
        self._agent_id = agent_id
        self._session_duration_hours = session_duration_hours

        # Create the underlying SDK client (used by CLI as well)
        self._client = SdkClient(api_key=self._api_key)

        # Ensure agent exists and has an active session
        self._ensure_agent(agent_pattern, agent_auto_create)

    def _ensure_agent(self, pattern: str, auto_create: bool) -> None:
        """Make sure the agent exists and a session is active."""
        if auto_create:
            try:
                # Check if agent exists
                agent = self._client.get_agent(self._agent_id)
            except Exception:
                agent = None

            if not agent:
                self._client.create_agent(
                    agent_id=self._agent_id,
                    pattern=pattern,
                )

        # Activate session (returns JWT token, stored internally)
        self._client.activate_session(
            agent_id=self._agent_id,
            duration_hours=self._session_duration_hours,
        )

    # ── Memory operations ────────────────────────────────────────────────

    def remember(
        self,
        memory: str,
        memory_type: str = "fact",
        confidence: Optional[float] = None,
        provenance: str = "explicit_statement",
        **kwargs,
    ) -> dict:
        """Store a memory into the agent's namespace.

        Args:
            memory: The textual content to remember.
            memory_type: One of the 13 allowed types.
            confidence: Optional confidence score (0.0–1.0).
            provenance: Source tag for the memory.

        Returns:
            API response dict.
        """
        params = {
            "memory": memory,
            "memory_type": memory_type,
            "provenance": provenance,
        }
        if confidence is not None:
            params["confidence"] = confidence
        params.update(kwargs)
        return self._client.remember(agent_id=self._agent_id, **params)

    def recall(
        self,
        query: str,
        memory_type: Optional[str] = None,
        top_k: int = 10,
        **kwargs,
    ) -> dict:
        """Semantic search over the agent's memories."""
        params = {"query": query, "top_k": top_k}
        if memory_type:
            params["memory_type"] = memory_type
        params.update(kwargs)
        return self._client.recall(agent_id=self._agent_id, **params)

    def recall_recent(self, top_k: int = 10) -> dict:
        """Retrieve the most recent memories (no query needed)."""
        return self._client.recall(
            agent_id=self._agent_id, query="", top_k=top_k
        )

    def recall_as_of(self, iso_date: str, query: str = "", top_k: int = 10) -> dict:
        """Point-in-time recall."""
        return self._client.recall(
            agent_id=self._agent_id,
            query=query,
            top_k=top_k,
            as_of=iso_date,
        )

    def recall_changed_since(self, iso_datetime: str, top_k: int = 10) -> dict:
        """Recall only memories created/modified after a given datetime."""
        return self._client.recall(
            agent_id=self._agent_id,
            query="",
            top_k=top_k,
            changed_since=iso_datetime,
        )

    def answer(self, question: str, **kwargs) -> dict:
        """Generate a grounded RAG answer from memory."""
        return self._client.answer(
            agent_id=self._agent_id, question=question, **kwargs
        )


__all__ = ["MemantoClient"]
