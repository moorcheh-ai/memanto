"""
Memanto Tools for LangChain and LangGraph

LangChain tool wrappers around Memanto's SdkClient for persistent,
long-term memory operations. These tools can be used in any LangChain
agent or LangGraph workflow.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, ConfigDict

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

# Valid Memanto memory types
VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)

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
# LangChain Tool classes
# ---------------------------------------------------------------------------


class MemantoRememberTool(BaseTool):
    """Store a memory in Memanto's persistent semantic database."""

    name: str = "memanto_remember"
    description: str = (
        "Store a structured memory in Memanto for long-term persistence. "
        "Use this to save facts, observations, decisions, preferences, or any "
        "information that should be available across sessions. "
        "Each memory has a type, title, content, confidence score, and optional tags."
    )
    args_schema: Type[BaseModel] = RememberInput
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: SdkClient = Field(exclude=True)
    agent_id: str

    def _run(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> str:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        try:
            result = self.client.remember(
                agent_id=self.agent_id,
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
        except Exception as e:
            return f"Error storing memory: {str(e)}"


class MemantoRecallTool(BaseTool):
    """Search and retrieve memories from Memanto's persistent database."""

    name: str = "memanto_recall"
    description: str = (
        "Search Memanto's persistent memory database using natural language. "
        "Returns stored memories ranked by semantic relevance. Use this to "
        "retrieve facts, findings, decisions, or any previously stored "
        "information from past sessions."
    )
    args_schema: Type[BaseModel] = RecallInput
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: SdkClient = Field(exclude=True)
    agent_id: str

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

        try:
            result = self.client.recall(
                agent_id=self.agent_id,
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
                lines.append(
                    f"  {i}. [{mem_type}] {title} (confidence: {confidence})\n"
                    f"     {content}\n"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"Error recalling memories: {str(e)}"


class MemantoAnswerTool(BaseTool):
    """Get AI-generated answers grounded in stored memories (RAG)."""

    name: str = "memanto_answer"
    description: str = (
        "Ask a question and get an AI-generated answer grounded in the agent's "
        "stored memories using Retrieval-Augmented Generation (RAG). Useful for "
        "synthesizing insights from multiple memories."
    )
    args_schema: Type[BaseModel] = AnswerInput
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: SdkClient = Field(exclude=True)
    agent_id: str

    def _run(self, question: str) -> str:
        try:
            result = self.client.answer(
                agent_id=self.agent_id,
                question=question,
            )

            answer = result.get("answer", "No answer could be generated.")
            sources = result.get("sources", [])
            
            output = f"Answer: {answer}"
            if sources:
                output += f"\n\nBased on {len(sources)} memory source(s)."
                
            return output
        except Exception as e:
            return f"Error generating answer: {str(e)}"


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> List[BaseTool]:
    """
    Create all Memanto tools bound to a specific client and agent.

    Returns:
        List of tool instances: [remember, recall, answer]
    """
    return [
        MemantoRememberTool(client=client, agent_id=agent_id),
        MemantoRecallTool(client=client, agent_id=agent_id),
        MemantoAnswerTool(client=client, agent_id=agent_id),
    ]
