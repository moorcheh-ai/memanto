"""
tools.py
========
Memanto operations exposed as LangChain/LangGraph tools.

Architecture:
  LangGraph manages graph state (conversation flow).
  Memanto tools are the ONLY memory layer — no LangGraph checkpointer for long-term memory.

The agent node decides WHEN to call these tools.
Memanto stores the memories on Moorcheh's cloud — they persist across ALL sessions.
"""
from __future__ import annotations
from typing import Optional
from langchain_core.tools import tool
from memanto_client import MeMantoClient

# Module-level client — shared across all tool calls in a session
_client: Optional[MeMantoClient] = None


def init_tools(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    agent_id: str = "langgraph-agent",
) -> MeMantoClient:
    """Call once at startup to initialise the shared Memanto client."""
    global _client
    _client = MeMantoClient(base_url=base_url, api_key=api_key, agent_id=agent_id)
    return _client


def _get_client() -> MeMantoClient:
    if _client is None:
        raise RuntimeError("Call init_tools() before using Memanto tools.")
    return _client


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def remember_fact(content: str, tags: str = "") -> str:
    """
    Persist a fact, finding, or observation to Memanto permanent memory.
    Call this when you learn something worth remembering across sessions.
    tags: comma-separated list e.g. 'user,preference,python'
    Returns the memory ID (save it if you may need to correct it later).
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    mem = _get_client().remember(content=content, memory_type="fact", tags=tag_list)
    mid = mem.get("id","unknown")
    return f"✅ Stored memory [{mid}]: {content[:100]}"


@tool
def remember_preference(content: str) -> str:
    """
    Persist a user preference to Memanto memory.
    Use for things like: communication style, format preferences, recurring goals.
    Returns the memory ID.
    """
    mem = _get_client().remember(content=content, memory_type="preference", tags=["preference","user"])
    mid = mem.get("id","unknown")
    return f"✅ Stored preference [{mid}]: {content[:100]}"


@tool
def remember_decision(content: str) -> str:
    """
    Persist a key decision or conclusion to Memanto memory.
    Returns the memory ID.
    """
    mem = _get_client().remember(content=content, memory_type="decision", tags=["decision"])
    mid = mem.get("id","unknown")
    return f"✅ Stored decision [{mid}]: {content[:100]}"


@tool
def recall_memory(query: str, limit: int = 5) -> str:
    """
    Search Memanto's permanent memory for relevant context.
    ALWAYS call this at the START of a new session or when the user references past work.
    This is the core cross-session recall mechanism.
    query: natural language question e.g. 'what did the user ask about last time?'
    """
    results = _get_client().recall(query=query, limit=limit)
    if not results:
        return "📭 No relevant memories found. This may be a fresh topic."
    lines = [f"  [{r.get('id','?')}] {r.get('content','')[:150]}" for r in results]
    return "📚 Retrieved memories:\n" + "\n".join(lines)


@tool
def recall_preferences(query: str) -> str:
    """
    Retrieve stored user preferences from Memanto.
    Call at the start of every session to personalise responses.
    query: topic to filter by, e.g. 'user preferences' or 'communication style'
    """
    results = _get_client().recall(query=query, limit=5, memory_type="preference")
    if not results:
        return "No stored preferences found."
    lines = [f"  • {r.get('content','')}" for r in results]
    return "👤 User preferences:\n" + "\n".join(lines)


@tool
def answer_from_memory(question: str) -> str:
    """
    Generate a grounded RAG answer using Memanto's stored memories.
    Use when you need to synthesise multiple past findings into one answer.
    """
    answer = _get_client().answer(question)
    return f"🧠 Memory-grounded answer: {answer}" if answer else "No answer generated from memory."


@tool
def correct_memory(old_content: str, new_content: str) -> str:
    """
    Handle a contradictory or outdated memory.
    Stores the corrected fact as a new memory via POST /remember.
    The previous fact is included in metadata.previous_content so applications
    can maintain an audit trail.
    old_content: the outdated fact being replaced.
    new_content: the corrected, up-to-date fact.
    """
    updated = _get_client().correct(old_content=old_content, new_content=new_content)
    mid = updated.get("id", "unknown")
    return (
        f"🔄 Contradiction resolved. New memory [{mid}] stored.\n"
        f"   New fact: {new_content[:120]}\n"
        f"   Old fact archived in metadata.previous_content."
    )


# Exported list for binding to the agent
MEMANTO_TOOLS = [
    remember_fact,
    remember_preference,
    remember_decision,
    recall_memory,
    recall_preferences,
    answer_from_memory,
    correct_memory,
]