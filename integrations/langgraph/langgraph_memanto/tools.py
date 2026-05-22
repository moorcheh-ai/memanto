"""
Memanto Tools for LangGraph.

LangChain/LangGraph tool wrappers around Memanto's SdkClient for persistent,
cross-session memory operations. These tools let LangGraph agents store
and retrieve memories that survive across sessions.

Three primitives:
  - remember: Store a typed memory with confidence score
  - recall:   Search memories by semantic similarity
  - answer:   Get an AI-generated answer grounded in stored memories (RAG)

The tools are LangChain ``@tool`` functions, so they work with both
LangGraph StateGraph workflows and LangChain ReAct agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient

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


# ---------------------------------------------------------------------------
# Input schemas (Pydantic models for structured tool calls)
# ---------------------------------------------------------------------------


class RememberInput(BaseModel):
    """Input schema for the Memanto remember tool."""

    memory_type: str = Field(
        ...,
        description=(
            f"The semantic type of memory to store. Must be exactly one of: "
            f"fact, preference, goal, decision, artifact, learning, event, "
            f"instruction, relationship, context, observation, commitment, "
            f"or error. Context definitions: {VALID_MEMORY_TYPES}"
        ),
    )
    title: str = Field(
        ...,
        description="Short title for the memory (max 100 characters).",
    )
    content: str = Field(
        ...,
        description="The memory content to store (max 10000 characters). Be concise and atomic.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score from 0.0 to 1.0. The agent must evaluate the certainty "
            "of the memory. Use 1.0 for verified explicit facts, 0.7-0.85 for "
            "observations/estimates, and lower for unverified information."
        ),
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags for categorization (e.g. 'support,billing,refund'). Use lowercase.",
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
# Tool factory — creates @tool functions bound to a specific SdkClient
# ---------------------------------------------------------------------------


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> dict[str, Any]:
    """
    Create Memanto remember/recall/answer tools bound to a specific client and agent.

    Returns:
        Dict with keys ``'remember'``, ``'recall'``, ``'answer'`` mapping to
        LangChain ``@tool`` instances that can be used in LangGraph workflows
        or LangChain ReAct agents.

    Usage::

        tools = create_memanto_tools(client, agent_id="support-agent")
        graph.add_node("remember", tools["remember"])
        # OR with a ReAct agent:
        agent = create_react_agent(llm, list(tools.values()))
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
        information that should be available to other agents or future sessions.
        Each memory has a type, title, confidence score, and optional tags.
        """
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
        stored information from any agent that shares this memory namespace.
        """
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
            mem_title = mem.get("title", "Untitled")
            mem_content = mem.get("content", "")
            mem_type = mem.get("type", "unknown")
            mem_confidence = mem.get("confidence", "N/A")
            mem_tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(mem_tags)}]" if mem_tags else ""

            lines.append(
                f"  {i}. [{mem_type}] {mem_title} (confidence: {mem_confidence}){tag_str}\n"
                f"     {mem_content}\n"
            )

        return "\n".join(lines)

    @tool(args_schema=AnswerInput)
    def memanto_answer(question: str) -> str:
        """Ask a question and get an AI-generated answer grounded in the agent's
        stored memories using Retrieval-Augmented Generation (RAG).

        This is useful for synthesizing insights from multiple stored memories
        into a coherent answer.
        """
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

    return {
        "remember": memanto_remember,
        "recall": memanto_recall,
        "answer": memanto_answer,
    }


# ---------------------------------------------------------------------------
# Standalone Tool classes (alternative to factory functions)
# ---------------------------------------------------------------------------


class MemantoRememberTool:
    """
    Store a memory in Memanto's persistent semantic database.

    Can be used as a node function in a LangGraph StateGraph::

        tool = MemantoRememberTool(client, agent_id)
        graph.add_node("remember", tool)
    """

    def __init__(self, client: SdkClient, agent_id: str) -> None:
        self._client = client
        self._agent_id = agent_id
        self.name = "memanto_remember"
        self.description = (
            "Store a structured memory in Memanto for long-term persistence. "
            "Use this to save facts, observations, decisions, preferences, or any "
            "information that should be available to other agents or future sessions."
        )

    def __call__(self, **kwargs: Any) -> str:
        tools = create_memanto_tools(self._client, self._agent_id)
        return tools["remember"].invoke(kwargs)

    def as_langchain_tool(self):
        """Return the LangChain @tool version."""
        return create_memanto_tools(self._client, self._agent_id)["remember"]


class MemantoRecallTool:
    """Search and retrieve memories from Memanto's persistent database."""

    def __init__(self, client: SdkClient, agent_id: str) -> None:
        self._client = client
        self._agent_id = agent_id
        self.name = "memanto_recall"
        self.description = (
            "Search Memanto's persistent memory database using natural language. "
            "Returns stored memories ranked by semantic relevance."
        )

    def __call__(self, **kwargs: Any) -> str:
        tools = create_memanto_tools(self._client, self._agent_id)
        return tools["recall"].invoke(kwargs)

    def as_langchain_tool(self):
        """Return the LangChain @tool version."""
        return create_memanto_tools(self._client, self._agent_id)["recall"]


class MemantoAnswerTool:
    """Get AI-generated answers grounded in stored memories (RAG)."""

    def __init__(self, client: SdkClient, agent_id: str) -> None:
        self._client = client
        self._agent_id = agent_id
        self.name = "memanto_answer"
        self.description = (
            "Ask a question and get an AI-generated answer grounded in the agent's "
            "stored memories using Retrieval-Augmented Generation (RAG)."
        )

    def __call__(self, **kwargs: Any) -> str:
        tools = create_memanto_tools(self._client, self._agent_id)
        return tools["answer"].invoke(kwargs)

    def as_langchain_tool(self):
        """Return the LangChain @tool version."""
        return create_memanto_tools(self._client, self._agent_id)["answer"]
