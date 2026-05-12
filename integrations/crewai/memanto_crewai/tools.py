"""
Memanto Tools for CrewAI

CrewAI tool wrappers around Memanto's SdkClient for persistent,
cross-agent memory operations. These tools let CrewAI agents store
and retrieve memories that survive across sessions and agents.
"""

from __future__ import annotations

import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

# Valid Memanto memory types for reference in tool descriptions
VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class MemantoSetup:
    """
    Manages Memanto agent lifecycle for CrewAI integration.

    Handles agent creation, session activation, and teardown so that
    CrewAI scripts can focus on task orchestration.
    """

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
        logger.info("Activated session for agent '%s'", agent_id)
        return self.client

    def teardown(self, agent_id: str) -> None:
        """Deactivate the agent session."""
        try:
            self.client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent '%s'", agent_id)
        except Exception as e:
            logger.warning("Failed to deactivate agent '%s': %s", agent_id, e)


# ---------------------------------------------------------------------------
# Tool input schemas
# ---------------------------------------------------------------------------


class RememberInput(BaseModel):
    """Input schema for the Memanto remember tool."""

    memory_type: str = Field(
        ...,
        description=(
            f"The semantic type of memory to store. Must be one of: {VALID_MEMORY_TYPES}"
        ),
    )
    title: str = Field(
        ...,
        description="Short title for the memory (max 100 characters).",
    )
    content: str = Field(
        ...,
        description="The memory content to store (max 500 characters). Be concise and atomic.",
    )
    confidence: float = Field(
        default=0.85,
        description="Confidence score from 0.0 to 1.0. Use 1.0 for explicit facts, 0.7-0.85 for observations.",
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags for categorization (e.g. 'market,ai,trend'). Use lowercase.",
    )


class RecallInput(BaseModel):
    """Input schema for the Memanto recall tool."""

    query: str = Field(
        ...,
        description="Natural language search query to find relevant memories.",
    )
    limit: int = Field(
        default=5,
        description="Maximum number of memories to retrieve (1-20).",
    )
    memory_types: str = Field(
        default="",
        description=(
            "Comma-separated memory types to filter by "
            "(e.g. 'fact,observation'). Leave empty for all types."
        ),
    )


class AnswerInput(BaseModel):
    """Input schema for the Memanto answer tool."""

    question: str = Field(
        ...,
        description="A question to answer using RAG over the agent's stored memories.",
    )


# ---------------------------------------------------------------------------
# CrewAI Tool classes
# ---------------------------------------------------------------------------


class MemantoRememberTool(BaseTool):
    """Store a memory in Memanto's persistent semantic database."""

    name: str = "memanto_remember"
    description: str = (
        "Store a structured memory in Memanto for long-term persistence. "
        "Use this to save facts, observations, decisions, preferences, or any "
        "information that should be available to other agents or future sessions. "
        "Each memory has a type, title (max 100 chars), content (max 500 chars), "
        "confidence score, and optional tags."
    )
    args_schema: type[BaseModel] = RememberInput

    # Injected at construction time
    _client: SdkClient
    _agent_id: str

    def __init__(self, client: SdkClient, agent_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_agent_id", agent_id)

    def _run(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> str:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        result = self._client.remember(
            agent_id=self._agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tag_list,
            source="crewai-agent",
            provenance="explicit_statement",
        )

        return (
            f"Memory stored successfully.\n"
            f"  ID: {result['memory_id']}\n"
            f"  Type: {memory_type}\n"
            f"  Title: {title}\n"
            f"  Confidence: {confidence}"
        )


class MemantoRecallTool(BaseTool):
    """Search and retrieve memories from Memanto's persistent database."""

    name: str = "memanto_recall"
    description: str = (
        "Search Memanto's persistent memory database using natural language. "
        "Returns stored memories ranked by semantic relevance. Use this to "
        "retrieve facts, research findings, decisions, or any previously "
        "stored information from any agent that shares this memory namespace."
    )
    args_schema: type[BaseModel] = RecallInput

    _client: SdkClient
    _agent_id: str

    def __init__(self, client: SdkClient, agent_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_agent_id", agent_id)

    def _run(
        self,
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> str:
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types
            else None
        )

        result = self._client.recall(
            agent_id=self._agent_id,
            query=query,
            limit=min(limit, 20),
            type=type_list,
        )

        memories = result.get("memories", [])
        if not memories:
            return f"No memories found for query: '{query}'"

        lines = [f"Found {len(memories)} memories for '{query}':\n"]
        for i, mem in enumerate(memories, 1):
            title = mem.get("title", "Untitled")
            content = mem.get("content", "")
            mem_type = mem.get("type", "unknown")
            confidence = mem.get("confidence", "N/A")
            tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(tags)}]" if tags else ""

            lines.append(
                f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
                f"     {content}\n"
            )

        return "\n".join(lines)


class MemantoAnswerTool(BaseTool):
    """Get AI-generated answers grounded in stored memories (RAG)."""

    name: str = "memanto_answer"
    description: str = (
        "Ask a question and get an AI-generated answer grounded in the agent's "
        "stored memories using Retrieval-Augmented Generation (RAG). This is "
        "useful for synthesizing insights from multiple stored memories into "
        "a coherent answer."
    )
    args_schema: type[BaseModel] = AnswerInput

    _client: SdkClient
    _agent_id: str

    def __init__(self, client: SdkClient, agent_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_agent_id", agent_id)

    def _run(self, question: str) -> str:
        result = self._client.answer(
            agent_id=self._agent_id,
            question=question,
        )

        answer = result.get("answer", "No answer could be generated.")
        sources = result.get("sources", [])

        output = f"Answer: {answer}"
        if sources:
            output += f"\n\nBased on {len(sources)} memory source(s)."

        return output


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> dict[str, BaseTool]:
    """
    Create all Memanto tools bound to a specific client and agent.

    Returns:
        Dict with keys 'remember', 'recall', 'answer' mapping to tool instances.
    """
    return {
        "remember": MemantoRememberTool(client=client, agent_id=agent_id),
        "recall": MemantoRecallTool(client=client, agent_id=agent_id),
        "answer": MemantoAnswerTool(client=client, agent_id=agent_id),
    }
