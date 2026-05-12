"""
Memanto Tools for LangGraph integration.

Wraps the Memanto SDK remember / recall / answer API into LangChain
Tool objects so they can be used inside a LangGraph agent.

Uses Pydantic v2 schemas (Zod v4-compatible) for structured input.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic v2 schemas (Zod v4 compatible)
# ---------------------------------------------------------------------------

class RememberInput(BaseModel):
    """Schema for the remember tool."""
    content: str = Field(
        ...,
        description="The fact or piece of information to store in long-term memory.",
        min_length=1,
        max_length=500,
    )
    memory_type: str = Field(
        default="semantic",
        description="Type of memory: semantic, episodic, or procedural.",
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags for categorising this memory.",
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


class RecallInput(BaseModel):
    """Schema for the recall tool."""
    query: str = Field(
        ...,
        description="Natural-language query to search persisted memories.",
        min_length=1,
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of memories to retrieve.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be empty")
        return v


class AnswerInput(BaseModel):
    """Schema for the answer tool — synthesises across memories."""
    question: str = Field(
        ...,
        description="A complex question that requires synthesising multiple memories.",
        min_length=1,
    )

    @field_validator("question")
    @classmethod
    def question_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be empty")
        return v


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

_MEMANTO_NAMESPACE = os.getenv("MEMANTO_NAMESPACE", "langgraph-agent")


def _get_memanto_client():
    """Lazy-load the Memanto SDK client."""
    from moorcheh_sdk import MoorchehClient  # type: ignore[import-untyped]
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError("MOORCHEH_API_KEY environment variable is required")
    return MoorchehClient(api_key=api_key)


@tool(args_schema=RememberInput)
def memanto_remember(content: str, memory_type: str = "semantic", tags: str = "") -> str:
    """Store a fact in long-term memory via Memanto. Use this whenever you learn
    something new about the user — their name, preferences, issue history, etc."""
    client = _get_memanto_client()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    result = client.add_memory(
        namespace=_MEMANTO_NAMESPACE,
        content=content,
        memory_type=memory_type,
        tags=tag_list,
    )
    return f"✅ Memory stored: {content[:80]}{'...' if len(content) > 80 else ''}"


@tool(args_schema=RecallInput)
def memanto_recall(query: str, top_k: int = 5) -> str:
    """Recall previously stored memories from Memanto. Always call this at the
    start of a conversation to retrieve cross-session context about the user."""
    client = _get_memanto_client()
    result = client.search_memory(
        namespace=_MEMANTO_NAMESPACE,
        query=query,
        top_k=top_k,
    )
    if not result:
        return "No memories found for this query."
    formatted = []
    for i, mem in enumerate(result, 1):
        content = mem if isinstance(mem, str) else mem.get("content", str(mem))
        formatted.append(f"{i}. {content}")
    return "\n".join(formatted)


@tool(args_schema=AnswerInput)
def memanto_answer(question: str) -> str:
    """Synthesise an answer across multiple memories stored in Memanto. Use
    when the user asks a complex question that requires combining several
    stored facts."""
    client = _get_memanto_client()
    result = client.answer(
        namespace=_MEMANTO_NAMESPACE,
        question=question,
    )
    return result if isinstance(result, str) else str(result)