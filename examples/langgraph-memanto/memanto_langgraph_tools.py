"""
Memanto Tools for LangGraph

LangGraph tool wrappers around Memanto's SdkClient for persistent,
cross-session memory operations. These tools let LangGraph agents store
and retrieve memories that survive across sessions, agents, and runs.

This integration demonstrates how Memanto acts as a long-term memory
layer for LangGraph agents — going beyond the standard LangGraph state
to provide true cross-session persistence.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient
from memanto.app.utils.errors import AgentAlreadyExistsError

logger = logging.getLogger(__name__)

# Valid Memanto memory types with definitions for the LLM
VALID_MEMORY_TYPES = (
    "fact (objective truths/data), "
    "preference (user likes/dislikes), "
    "goal (objectives/targets), "
    "decision (choices made/agreed upon), "
    "artifact (files/code/deliverables), "
    "learning (insights/lessons learned), "
    "event (occurrences/meetings), "
    "instruction (how-tos/directives), "
    "relationship (connections between entities), "
    "context (background info/state), "
    "observation (trends/patterns/notices), "
    "commitment (promises/next steps), "
    "error (failures/mistakes)"
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
        except AgentAlreadyExistsError:
            logger.info("Memanto agent '%s' already exists, reusing", agent_id)
        except Exception as e:
            logger.error("Failed to create agent '%s': %s", agent_id, e)
            raise

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
            f"The semantic type of memory to store. Must be exactly one of: "
            f"fact, preference, goal, decision, artifact, learning, event, "
            f"instruction, relationship, context, observation, commitment, or error. "
            f"Context: {VALID_MEMORY_TYPES}"
        ),
    )
    title: str = Field(
        ...,
        description="Short title for the memory (max 100 characters).",
    )
    content: str = Field(
        ...,
        description="The memory content to store. Be concise and atomic.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score from 0.0 to 1.0. Use 1.0 for verified facts, "
            "0.7-0.85 for observations, lower for unverified information."
        ),
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags for categorization (e.g. 'research,ai,trend').",
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
        description="Comma-separated memory types to filter by (e.g. 'fact,observation').",
    )


class AnswerInput(BaseModel):
    """Input schema for the Memanto answer tool."""

    question: str = Field(
        ...,
        description="A question to answer using RAG over the agent's stored memories.",
    )


# ---------------------------------------------------------------------------
# LangGraph tool functions
# ---------------------------------------------------------------------------


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> list:
    """
    Create all Memanto tools bound to a specific client and agent.

    Returns a list of LangChain @tool-decorated functions suitable for
    use with LangGraph's create_react_agent or ToolNode.

    Args:
        client: An active SdkClient with a valid session.
        agent_id: The Memanto agent ID to bind tools to.

    Returns:
        List of three tool functions: remember, recall, answer.
    """
    _client = client
    _agent_id = agent_id

    @tool(args_schema=RememberInput)
    def memanto_remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: str = "",
    ) -> str:
        """Store a structured memory in Memanto for long-term persistence.
        Use this to save facts, observations, decisions, preferences, or any
        information that should be available across sessions and agents."""
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        result = _client.remember(
            agent_id=_agent_id,
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

    @tool(args_schema=RecallInput)
    def memanto_recall(
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> str:
        """Search Memanto's persistent memory database using natural language.
        Returns stored memories ranked by semantic relevance. Use this to
        retrieve facts, research findings, decisions, or any previously
        stored information — including memories from previous sessions."""
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types
            else None
        )

        result = _client.recall(
            agent_id=_agent_id,
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

    @tool(args_schema=AnswerInput)
    def memanto_answer(question: str) -> str:
        """Ask a question and get an AI-generated answer grounded in the agent's
        stored memories using Retrieval-Augmented Generation (RAG). This is
        useful for synthesizing insights from multiple stored memories into
        a coherent answer."""
        result = _client.answer(
            agent_id=_agent_id,
            question=question,
        )

        answer = result.get("answer", "No answer could be generated.")
        sources = result.get("sources", [])

        output = f"Answer: {answer}"
        if sources:
            output += f"\n\nBased on {len(sources)} memory source(s)."

        return output

    return [memanto_remember, memanto_recall, memanto_answer]
