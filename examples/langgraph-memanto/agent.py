"""
LangGraph agent with Memanto persistent memory tools.

Provides a ReAct-style agent that can store, search, and reason over
memories that survive across sessions. Built on LangGraph's
create_react_agent with Memanto's SdkClient for memory operations.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool as langchain_tool
from langgraph.prebuilt import create_react_agent
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class MemantoSetup:
    """Manage Memanto agent lifecycle for LangGraph integration."""

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
                agent_id=agent_id, pattern=pattern, description=description
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


def create_memanto_tools(client: SdkClient, agent_id: str) -> dict[str, Any]:
    """Build LangChain-compatible tools backed by Memanto memory operations.

    Returns a dict with keys 'remember', 'recall', 'answer'.
    """

    @langchain_tool
    def memanto_remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> str:
        """Store a structured memory in Memanto for long-term persistence.

        Use this to save facts, observations, decisions, preferences, or any
        information that should be available to future sessions or other agents.
        Each memory has a semantic type and confidence score.

        Args:
            memory_type: One of: fact, preference, goal, decision, artifact,
                learning, event, instruction, relationship, context, observation,
                commitment, error.
            title: Short title for the memory (max 100 characters).
            content: The memory content to store. Be concise and atomic.
            confidence: Confidence score from 0.0 to 1.0. Use 1.0 for explicit
                facts stated by the user, 0.7-0.85 for observations.
            tags: Comma-separated tags for categorization (e.g. 'bug,ui,dark-mode').
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

    @langchain_tool
    def memanto_recall(
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> str:
        """Search Memanto's persistent memory using natural language.

        Returns stored memories ranked by semantic relevance. Use this to
        retrieve facts, past interactions, decisions, or any previously stored
        information from this agent's memory namespace. Memories survive across
        sessions -- an agent can recall what happened "yesterday."

        Args:
            query: Natural language search query to find relevant memories.
            limit: Maximum number of memories to retrieve (1-20).
            memory_types: Comma-separated memory types to filter by
                (e.g. 'fact,preference'). Leave empty for all types.
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
            tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
            lines.append(
                f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
                f"     {content}\n"
            )
        return "\n".join(lines)

    @langchain_tool
    def memanto_answer(question: str) -> str:
        """Ask a question and get an AI-generated answer grounded in stored memories.

        Uses Retrieval-Augmented Generation over the agent's Memanto memory
        namespace. Useful for synthesizing insights from multiple memories
        into a coherent answer.

        Args:
            question: A question to answer based on the agent's stored memories.
        """
        result = client.answer(agent_id=agent_id, question=question)
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


def build_agent(
    client: SdkClient,
    agent_id: str,
    system_prompt: str,
    model: str = "gpt-4o-mini",
) -> Any:
    """Build a LangGraph ReAct agent with Memanto memory tools.

    Args:
        client: An activated SdkClient instance.
        agent_id: The Memanto agent ID for memory operations.
        system_prompt: System prompt for the agent.
        model: LLM model identifier for the agent's reasoning.

    Returns:
        A compiled LangGraph agent ready to invoke.
    """
    tools_map = create_memanto_tools(client, agent_id)
    tools = list(tools_map.values())

    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
    )
    return agent
