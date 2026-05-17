"""
Memanto integration wrapper for LangGraph.

Provides typed persistence layer for storing and retrieving
agent memories across sessions via the Moorcheh API.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class MemantoMemory:
    """A lightweight wrapper around the Moorcheh Memanto API.

    Stores memories as typed JSON blobs with metadata for
    cross-session recall by LangGraph agents.
    """

    MEMORY_TYPES = {
        "fact": "Verifiable factual statement about the user or world",
        "preference": "User preference, like or dislike",
        "observation": "Observation made during a conversation",
        "decision": "A decision made by the agent",
        "summary": "A summarized recollection of prior turns",
    }

    def __init__(self, api_key: str | None = None, agent_id: str = "langgraph-support-agent"):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.agent_id = agent_id
        self._client = self._init_client()

    def _init_client(self) -> Any:
        """Initialize the Moorcheh SDK client."""
        try:
            from moorcheh_sdk import MoorchehClient
            return MoorchehClient(api_key=self.api_key)
        except ImportError:
            raise ImportError(
                "moorcheh_sdk not installed. Run: pip install moorcheh-sdk"
            )

    # ── Write ──────────────────────────────────────────────────────────

    def store(self, memory_type: str, title: str, content: str, confidence: float = 1.0) -> dict:
        """Store a memory in Memanto.

        Args:
            memory_type: One of 'fact', 'preference', 'observation', 'decision', 'summary'
            title: Short identifier (e.g. 'user_name', 'preference:color')
            content: The memory content
            confidence: 0.0 to 1.0
        """
        if memory_type not in self.MEMORY_TYPES:
            raise ValueError(f"Invalid memory type: {memory_type}. Choose from {list(self.MEMORY_TYPES)}")

        payload = {
            "type": memory_type,
            "title": title[:100],
            "content": content,
            "confidence": confidence,
            "agent_id": self.agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": "langgraph_agent",
        }
        return self._client.create_memory(**payload)

    def store_fact(self, key: str, value: str) -> dict:
        """Convenience: store a factual memory."""
        return self.store("fact", key, value, confidence=1.0)

    def store_preference(self, key: str, value: str) -> dict:
        """Convenience: store a user preference."""
        return self.store("preference", key, value, confidence=0.8)

    def store_conversation_summary(self, summary: str) -> dict:
        """Store a summary of a conversation turn."""
        return self.store("summary", f"summary_{datetime.now(timezone.utc).isoformat()}", summary, confidence=0.9)

    # ── Read ────────────────────────────────────────────────────────────

    def recall(self, query: str, limit: int = 10) -> list[dict]:
        """Search memories by semantic similarity to *query*.

        Returns list of matching memory dicts, newest first.
        """
        return self._client.search_memories(
            query=query,
            agent_id=self.agent_id,
            limit=limit,
        )

    def recall_all(self) -> list[dict]:
        """Fetch all memories for this agent, newest first."""
        return self._client.list_memories(agent_id=self.agent_id)

    def recall_by_type(self, memory_type: str, limit: int = 20) -> list[dict]:
        """Fetch memories of a specific type."""
        return self._client.search_memories(
            query="",
            agent_id=self.agent_id,
            filters={"type": memory_type},
            limit=limit,
        )

    def format_context(self, memories: list[dict], max_chars: int = 3000) -> str:
        """Format memories into a prompt context string for the LLM.

        This is what provides the 'memory context' to the LangGraph agent.
        """
        if not memories:
            return "No prior memories found."

        parts = []
        total = 0
        for m in memories:
            entry = f"- [{m.get('type', '?')}] {m.get('title', '')}: {m.get('content', '')}"
            total += len(entry)
            if total > max_chars:
                break
            parts.append(entry)

        return "## Prior Memories\n" + "\n".join(parts)

    # ── Utility ─────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Clear all memories for this agent (for testing)."""
        for m in self.recall_all():
            self._client.delete_memory(m["id"])
