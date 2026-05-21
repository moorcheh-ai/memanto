"""
Memanto Tools for LangGraph

LangGraph-compatible tool functions wrapping Memanto's SdkClient for
persistent, cross-session memory operations. These tools let LangGraph
agents store and retrieve memories that survive across sessions.

Usage:
    from memanto_tools import create_memanto_toolkit

    toolkit = create_memanto_toolkit(api_key="...", agent_id="my-agent")
    remember_fn = toolkit["remember"]
    recall_fn = toolkit["recall"]
    answer_fn = toolkit["answer"]
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

# Valid Memanto memory types
VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class MemantoToolkit:
    """
    Manages Memanto agent lifecycle and provides tool functions
    compatible with LangGraph's ToolNode.

    Attributes:
        client: The underlying Memanto SDK client.
        agent_id: The agent identifier used for memory operations.
    """

    def __init__(self, api_key: str) -> None:
        self.client = SdkClient(api_key=api_key)
        self.agent_id: str | None = None

    def setup(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
        duration_hours: int = 6,
    ) -> None:
        """
        Create agent (if needed) and activate a session.

        Args:
            agent_id: Unique identifier for the agent.
            pattern: Agent pattern — "support", "project", or "tool".
            description: Optional description.
            duration_hours: Session lifetime in hours.
        """
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=description,
            )
            logger.info("Created Memanto agent '%s'", agent_id)
        except Exception:
            logger.info("Memanto agent '%s' already exists, reusing", agent_id)

        self.client.activate_agent(agent_id, duration_hours=duration_hours)
        self.agent_id = agent_id
        logger.info("Activated session for agent '%s'", agent_id)

    def teardown(self) -> None:
        """Deactivate the agent session."""
        if self.agent_id:
            try:
                self.client.deactivate_agent(self.agent_id)
                logger.info("Deactivated session for agent '%s'", self.agent_id)
            except Exception as e:
                logger.warning("Failed to deactivate agent '%s': %s", self.agent_id, e)

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Store a memory in Memanto.

        Args:
            memory_type: One of: fact, preference, goal, decision, artifact,
                learning, event, instruction, relationship, context,
                observation, commitment, error.
            title: Short title (max 100 chars).
            content: Memory content (max 10000 chars).
            confidence: Confidence score 0.0–1.0.
            tags: Optional list of tags.

        Returns:
            Dict with memory_id, status, confidence.
        """
        if not self.agent_id:
            raise RuntimeError("Agent not initialized. Call setup() first.")

        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-agent",
            provenance="explicit_statement",
        )

        return {
            "memory_id": result["memory_id"],
            "status": "stored",
            "memory_type": memory_type,
            "title": title,
            "confidence": confidence,
        }

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Search memories by semantic similarity.

        Args:
            query: Natural-language search query.
            limit: Max results (1–20).
            memory_types: Optional list of types to filter by.

        Returns:
            Dict with memories list and count.
        """
        if not self.agent_id:
            raise RuntimeError("Agent not initialized. Call setup() first.")

        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=min(limit, 20),
            type=memory_types,
        )

        memories = result.get("memories", [])
        return {
            "query": query,
            "memories": memories,
            "count": len(memories),
        }

    def answer(
        self,
        question: str,
    ) -> dict[str, Any]:
        """
        Get an AI-generated answer grounded in stored memories (RAG).

        Args:
            question: A question to answer using stored memories.

        Returns:
            Dict with answer text and sources.
        """
        if not self.agent_id:
            raise RuntimeError("Agent not initialized. Call setup() first.")

        result = self.client.answer(
            agent_id=self.agent_id,
            question=question,
        )

        return {
            "answer": result.get("answer", "No answer generated."),
            "sources": result.get("sources", []),
        }


def format_memories_for_context(memories: list[dict[str, Any]]) -> str:
    """Format recalled memories into a readable context string."""
    if not memories:
        return "No relevant memories found."

    lines = []
    for i, mem in enumerate(memories, 1):
        title = mem.get("title", "Untitled")
        content = mem.get("content", "")
        mem_type = mem.get("type", "unknown")
        confidence = mem.get("confidence", "N/A")
        tags = mem.get("tags", [])
        tag_str = f" [tags: {', '.join(tags)}]" if tags else ""

        lines.append(
            f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
            f"     {content}"
        )

    return "\n\n".join(lines)


def create_memanto_toolkit(
    api_key: str,
) -> MemantoToolkit:
    """
    Create a MemantoToolkit instance.

    Args:
        api_key: Moorcheh API key.

    Returns:
        MemantoToolkit instance. Call .setup(agent_id) before use.
    """
    return MemantoToolkit(api_key=api_key)
