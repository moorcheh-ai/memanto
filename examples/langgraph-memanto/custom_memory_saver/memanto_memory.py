"""
MemantoMemory — A LangGraph-compatible memory integration for Memanto.

Provides tools to remember, recall, and get LLM-grounded answers
from a Memanto-powered long-term memory layer.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Memanto client wrapper
# ---------------------------------------------------------------------------

MEMORY_CATEGORIES = [
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
]

MEMORY_TYPES_LITERAL = str  # one of the categories above


class MemantoMemory:
    """A thin Pythonic wrapper around the Memanto REST API.

    This wraps the three core primitives:
        remember(text, type) → store a fact
        recall(query)         → semantic search over stored memories
        answer(question)      → LLM-grounded answer from memories

    In production you'd use the moorcheh_sdk directly. Here we keep
    it as a simple HTTP client so the example is self-contained.
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_name: str = "langgraph-agent",
        base_url: str = "https://api.moorcheh.ai/v1",
    ):
        from memanto.cli.client.sdk_client import SdkClient

        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.agent_name = agent_name
        self.client = SdkClient(api_key=self.api_key)

    # -----------------------------------------------------------------------
    # Session lifecycle
    # -----------------------------------------------------------------------

    def ensure_agent(self) -> dict:
        """Create the agent if it doesn't exist yet."""
        try:
            self.client.create_agent(self.agent_name, pattern="tool")
            return {"status": "created"}
        except Exception:
            return {"status": "exists"}

    def activate_session(self) -> str:
        """Start a session and return a session token."""
        self.ensure_agent()
        self.client.activate_agent(self.agent_name)
        return "active"

    def deactivate_session(self) -> None:
        """End the current session."""
        try:
            self.client.deactivate_agent(self.agent_name)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Memory primitives
    # -----------------------------------------------------------------------

    def remember(
        self,
        text: str,
        memory_type: str = "observation",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Store a memory."""
        tags = metadata.get("tags", []) if metadata else []
        return self.client.remember(
            agent_id=self.agent_name,
            content=text,
            memory_type=memory_type,
            title="Observation",
            tags=tags,
            source="custom_memory_saver",
        )

    def recall(
        self,
        query: str,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[dict]:
        """Search across stored memories and return relevant results."""
        types = [memory_type] if memory_type else None
        res = self.client.recall(
            agent_id=self.agent_name, query=query, limit=limit, type=types
        )
        # Convert to expected format
        return [
            {
                "id": m.get("memory_id"),
                "text": m.get("content"),
                "type": m.get("type", "unknown"),
                "confidence": m.get("confidence", "N/A"),
                "created_at": m.get("created_at", ""),
            }
            for m in res.get("memories", [])
        ]

    def answer(self, question: str) -> str:
        """Ask a question grounded in stored memories (built-in RAG)."""
        res = self.client.answer(agent_id=self.agent_name, question=question)
        return res.get("answer", "")

    # -----------------------------------------------------------------------
    # Batch helpers
    # -----------------------------------------------------------------------

    def batch_remember(
        self, memories: list[tuple[str, str, dict[str, Any] | None]]
    ) -> dict:
        """Store up to 100 memories at once.

        Each tuple is (text, memory_type, metadata_or_None).
        """
        payload = []
        for text, memory_type, metadata in memories:
            tags = metadata.get("tags", []) if metadata else []
            payload.append(
                {
                    "content": text,
                    "type": memory_type,
                    "title": "Observation",
                    "tags": tags,
                    "source": "custom_memory_saver",
                    "confidence": 0.85,
                }
            )

        return self.client.batch_remember(agent_id=self.agent_name, memories=payload)


# ---------------------------------------------------------------------------
# LangGraph integration helpers
# ---------------------------------------------------------------------------


def build_memory_context(memories: list[dict]) -> str:
    """Format recalled memories as a natural-language context block."""
    if not memories:
        return ""

    lines = ["## Relevant Memories from Previous Sessions\n"]
    for i, m in enumerate(memories, 1):
        text = m.get("text", "")
        mtype = m.get("type", "unknown")
        conf = m.get("confidence", "N/A")
        ts = m.get("created_at", "")
        lines.append(f"  [{i}] ({mtype}, confidence={conf}) {text}")
        if ts:
            lines[-1] += f"  [stored: {ts}]"
    return "\n".join(lines)


def extract_memories_from_tool_calls(state: dict) -> list[dict]:
    """Extract facts worth remembering from the agent's last response."""
    memories = []

    # Pull out user messages as observations
    for msg in state.get("messages", []):
        if hasattr(msg, "type") and msg.type == "human":
            memories.append(
                {
                    "text": f"User said: {msg.content[:500]}",
                    "type": "context",
                }
            )

    # Pull out AI responses as learnings
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            # Only store the first AI response we find (most recent)
            memories.append(
                {
                    "text": f"Agent responded: {msg.content[:500]}",
                    "type": "learning",
                }
            )
            break

    return memories
