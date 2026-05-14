"""
Memanto Tools for LangChain/LangGraph

These tools allow LangGraph agents to interact with Memanto's persistent
semantic memory for cross-session and cross-agent recall.
"""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = (
    "fact, preference, goal, decision, artifact, learning, event, "
    "instruction, relationship, context, observation, commitment, error"
)


class RememberInput(BaseModel):
    """Input schema for the Memanto remember tool."""

    memory_type: str = Field(
        ...,
        description=f"The semantic type of memory to store. Must be one of: {VALID_MEMORY_TYPES}",
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
        default=0.85,
        description="Confidence score from 0.0 to 1.0. Use 1.0 for explicit facts, 0.7-0.85 for observations.",
    )
    tags: list[str] | None = Field(
        default=None,
        description="List of tags for categorization.",
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
    memory_types: list[str] | None = Field(
        default=None,
        description="List of memory types to filter by (e.g. ['fact', 'observation']).",
    )


class AnswerInput(BaseModel):
    """Input schema for the Memanto answer tool."""

    question: str = Field(
        ...,
        description="A question to answer using RAG over the agent's stored memories.",
    )


class MemantoRememberTool(BaseTool):
    """Store a memory in Memanto's persistent semantic database."""

    name: str = "memanto_remember"
    description: str = (
        "Store a structured memory in Memanto for long-term persistence. "
        "Use this to save facts, observations, decisions, preferences, or any "
        "information that should be available to future sessions or other agents. "
        "Each memory has a type, title, content, confidence score, and optional tags."
    )
    args_schema: type[BaseModel] = RememberInput

    client: SdkClient = Field(exclude=True)
    agent_id: str

    def _run(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> str:
        try:
            result = self.client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tags,
                source="langgraph-agent",
                provenance="explicit_statement",
            )
            return (
                f"Memory stored successfully.\n"
                f"  ID: {result['memory_id']}\n"
                f"  Type: {memory_type}\n"
                f"  Title: {title}"
            )
        except Exception as e:
            logger.error(f"Error in MemantoRememberTool: {e}")
            return f"Error storing memory: {str(e)}"


class MemantoRecallTool(BaseTool):
    """Search and retrieve memories from Memanto's persistent database."""

    name: str = "memanto_recall"
    description: str = (
        "Search Memanto's persistent memory database using natural language. "
        "Returns stored memories ranked by semantic relevance. Use this to "
        "retrieve facts, research findings, decisions, or any previously "
        "stored information from future/past sessions or other agents."
    )
    args_schema: type[BaseModel] = RecallInput

    client: SdkClient = Field(exclude=True)
    agent_id: str

    def _run(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> str:
        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=min(limit, 20),
                type=memory_types,
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
        except Exception as e:
            logger.error(f"Error in MemantoRecallTool: {e}")
            return f"Error recalling memories: {str(e)}"


class MemantoAnswerTool(BaseTool):
    """Get AI-generated answers grounded in stored memories (RAG)."""

    name: str = "memanto_answer"
    description: str = (
        "Ask a question and get an AI-generated answer grounded in the agent's "
        "stored memories using Retrieval-Augmented Generation (RAG). Use this "
        "to synthesize insights from past sessions into a coherent answer."
    )
    args_schema: type[BaseModel] = AnswerInput

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
            logger.error(f"Error in MemantoAnswerTool: {e}")
            return f"Error getting answer from memory: {str(e)}"


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> list[BaseTool]:
    """
    Create all Memanto tools bound to a specific client and agent for LangChain/LangGraph.
    """
    return [
        MemantoRememberTool(client=client, agent_id=agent_id),
        MemantoRecallTool(client=client, agent_id=agent_id),
        MemantoAnswerTool(client=client, agent_id=agent_id),
    ]
