"""
Memanto + LangGraph Integration: Tool Wrappers

LangGraph-compatible tool wrappers around Memanto's SdkClient for
persistent, cross-session memory operations. These tools work with
any LangGraph agent that supports the tool-calling pattern.

Unlike the CrewAI integration, these tools return plain dict results
that LangGraph agents can process directly in their state graph.
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class MemantoSetup:
    """Manages Memanto agent lifecycle for LangGraph integration."""

    def __init__(self, api_key: str) -> None:
        self.client = SdkClient(api_key=api_key)

    def setup(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
        duration_hours: int = 6,
    ) -> SdkClient:
        """Create agent (if needed) and activate a session."""
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
        return self.client

    def teardown(self, agent_id: str) -> None:
        """Deactivate the agent session."""
        try:
            self.client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent '%s'", agent_id)
        except Exception as e:
            logger.warning("Failed to deactivate agent '%s': %s", agent_id, e)


# ---------------------------------------------------------------------------
# LangGraph-compatible tool functions (return dicts, not strings)
# ---------------------------------------------------------------------------

def create_remember_tool(client: SdkClient, agent_id: str):
    """Create a remember tool callable for LangGraph agents."""

    def remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> dict[str, Any]:
        """Store a structured memory in Memanto for long-term persistence."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        result = client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tag_list,
            source="langgraph-agent",
            provenance="explicit_statement",
        )
        return {
            "status": "stored",
            "memory_id": result.get("memory_id", ""),
            "memory_type": memory_type,
            "title": title,
            "confidence": confidence,
        }

    return remember


def create_recall_tool(client: SdkClient, agent_id: str):
    """Create a recall tool callable for LangGraph agents."""

    def recall(
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> dict[str, Any]:
        """Search Memanto's persistent memory database."""
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types else None
        )
        result = client.recall(
            agent_id=agent_id,
            query=query,
            limit=min(limit, 20),
            type=type_list,
        )
        memories = result.get("memories", [])
        return {
            "status": "success",
            "query": query,
            "count": len(memories),
            "memories": [
                {
                    "title": m.get("title", "Untitled"),
                    "content": m.get("content", ""),
                    "memory_type": m.get("type", "unknown"),
                    "confidence": m.get("confidence", None),
                    "tags": m.get("tags", []),
                }
                for m in memories
            ],
        }

    return recall


def create_answer_tool(client: SdkClient, agent_id: str):
    """Create an answer tool callable for LangGraph agents."""

    def answer(question: str) -> dict[str, Any]:
        """Get an AI-generated answer grounded in stored memories (RAG)."""
        result = client.answer(agent_id=agent_id, question=question)
        return {
            "status": "success",
            "question": question,
            "answer": result.get("answer", "No answer available."),
            "source_count": len(result.get("sources", [])),
        }

    return answer


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> dict[str, Any]:
    """
    Create all Memanto tools bound to a specific client and agent.
    Returns a dict of LangGraph-compatible callables.
    """
    return {
        "remember": create_remember_tool(client, agent_id),
        "recall": create_recall_tool(client, agent_id),
        "answer": create_answer_tool(client, agent_id),
    }
