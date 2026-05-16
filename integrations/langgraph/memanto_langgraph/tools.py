"""
Memanto Tools for LangGraph

LangChain-compatible tool wrappers around Memanto's SdkClient for persistent,
cross-session memory operations. These tools let LangGraph agents store
and retrieve memories that survive across sessions and graph invocations.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class MemantoSetup:
    """
    Manages Memanto agent lifecycle for LangGraph integration.

    Handles agent creation, session activation, and teardown so that
    LangGraph scripts can focus on graph orchestration.
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


class RememberInput(BaseModel):
    """Input schema for the Memanto remember tool."""

    memory_type: str = Field(
        description=(
            f"The semantic type of memory to store. Must be one of: {VALID_MEMORY_TYPES}"
        ),
    )
    title: str = Field(
        description="Short title for the memory (max 100 characters).",
    )
    content: str = Field(
        description="The memory content to store (max 10000 characters). Be concise and atomic.",
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
        description="A question to answer using RAG over the agent's stored memories.",
    )


def create_memanto_remember_tool(client: SdkClient, agent_id: str):
    """Create a LangChain-compatible remember tool bound to a Memanto client."""

    @tool(args_schema=RememberInput)
    def memanto_remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> str:
        """Store a structured memory in Memanto for long-term persistence.

        Use this to save facts, observations, decisions, preferences, or any
        information that should be available to other agents or future sessions.
        Each memory has a type, title (max 100 chars), content (max 10000 chars),
        confidence score, and optional tags.
        """
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

        return (
            f"Memory stored successfully.\n"
            f"  ID: {result['memory_id']}\n"
            f"  Type: {memory_type}\n"
            f"  Title: {title}\n"
            f"  Confidence: {confidence}"
        )

    return memanto_remember


def create_memanto_recall_tool(client: SdkClient, agent_id: str):
    """Create a LangChain-compatible recall tool bound to a Memanto client."""

    @tool(args_schema=RecallInput)
    def memanto_recall(
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> str:
        """Search Memanto's persistent memory database using natural language.

        Returns stored memories ranked by semantic relevance. Use this to
        retrieve facts, research findings, decisions, or any previously
        stored information from any agent that shares this memory namespace.
        """
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types
            else None
        )

        result = client.recall(
            agent_id=agent_id,
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
            mem_tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(mem_tags)}]" if mem_tags else ""

            lines.append(
                f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
                f"     {content}\n"
            )

        return "\n".join(lines)

    return memanto_recall


def create_memanto_answer_tool(client: SdkClient, agent_id: str):
    """Create a LangChain-compatible answer tool bound to a Memanto client."""

    @tool(args_schema=AnswerInput)
    def memanto_answer(question: str) -> str:
        """Ask a question and get an AI-generated answer grounded in stored memories.

        This uses Retrieval-Augmented Generation (RAG) to synthesize insights
        from multiple stored memories into a coherent answer.
        """
        result = client.answer(
            agent_id=agent_id,
            question=question,
        )

        answer = result.get("answer", "No answer could be generated.")
        sources = result.get("sources", [])

        output = f"Answer: {answer}"
        if sources:
            output += f"\n\nBased on {len(sources)} memory source(s)."

        return output

    return memanto_answer


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> dict[str, Any]:
    """
    Create all Memanto tools bound to a specific client and agent.

    Returns:
        Dict with keys 'remember', 'recall', 'answer' mapping to tool instances.
    """
    return {
        "remember": create_memanto_remember_tool(client, agent_id),
        "recall": create_memanto_recall_tool(client, agent_id),
        "answer": create_memanto_answer_tool(client, agent_id),
    }


def get_all_tools(client: SdkClient, agent_id: str) -> list:
    """
    Get all Memanto tools as a list for binding to an LLM.

    Returns:
        List of all Memanto tools ready for use with LangGraph.
    """
    tools = create_memanto_tools(client, agent_id)
    return list(tools.values())
