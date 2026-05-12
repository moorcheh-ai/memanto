"""
Memanto Tools - Pydantic v2 schemas for LangGraph integration.
remember / recall / answer wrapped as LangChain tools.
"""
from __future__ import annotations
import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

NAMESPACE = os.getenv("MEMANTO_NAMESPACE", "langgraph-agent")

def _client():
    from moorcheh_sdk import MoorchehClient
    key = os.getenv("MOORCHEH_API_KEY")
    if not key:
        raise RuntimeError("MOORCHEH_API_KEY not set")
    return MoorchehClient(api_key=key)

class RememberInput(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    memory_type: str = Field(default="semantic")
    tags: str = Field(default="")
    @field_validator("content")
    @classmethod
    def not_empty(cls, v):
        if not v.strip(): raise ValueError("empty")
        return v

class RecallInput(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5)

class AnswerInput(BaseModel):
    question: str = Field(..., min_length=1)

@tool(args_schema=RememberInput)
def memanto_remember(content: str, memory_type: str = "semantic", tags: str = "") -> str:
    """Store a fact in long-term memory. Use when learning new info about the user."""
    c = _client()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    c.add_memory(namespace=NAMESPACE, content=content, memory_type=memory_type, tags=tag_list)
    return f"Stored: {content[:80]}"

@tool(args_schema=RecallInput)
def memanto_recall(query: str, top_k: int = 5) -> str:
    """Recall persisted memories. Call at start of conversation for cross-session context."""
    c = _client()
    results = c.search_memory(namespace=NAMESPACE, query=query, top_k=top_k)
    if not results:
        return "No memories found."
    return "\n".join(f"{i+1}. {m if isinstance(m,str) else m.get('content',str(m))}" for i,m in enumerate(results))

@tool(args_schema=AnswerInput)
def memanto_answer(question: str) -> str:
    """Synthesise answer across multiple memories. Use for complex multi-fact questions."""
    c = _client()
    result = c.answer(namespace=NAMESPACE, question=question)
    return result if isinstance(result, str) else str(result)

MEMORY_TOOLS = [memanto_remember, memanto_recall, memanto_answer]
