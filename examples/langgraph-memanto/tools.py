"""
Memanto operations exposed as LangGraph tools.

LangGraph:  orchestration, execution flow, session state
Memanto:    durable semantic memory
"""

from __future__ import annotations

from langchain_core.tools import tool
from memanto_client import MeMantoClient

_client: MeMantoClient | None = None


def init_tools(
    base_url: str | None = None,
    api_key: str | None = None,
    agent_id: str = "langgraph-agent",
) -> MeMantoClient:
    global _client
    _client = MeMantoClient(base_url=base_url, api_key=api_key, agent_id=agent_id)
    return _client


def _get_client() -> MeMantoClient:
    if _client is None:
        raise RuntimeError("Call init_tools() before using Memanto tools.")
    return _client


@tool
def remember_fact(content: str, tags: str = "") -> str:
    """
    Store an important fact or finding in long-term memory.
    Use for research findings, important discoveries, persistent observations.
    tags: comma-separated tags.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    memory = _get_client().remember(content=content, memory_type="fact", tags=tag_list)
    mid = memory.get("id")
    if not mid:
        return f"❌ Failed to store fact: {memory.get('error', 'unknown error')}"
    return f"✅ Stored fact [{mid}]: {content[:100]}"


@tool
def remember_preference(content: str) -> str:
    """
    Store a persistent user preference.
    Examples: communication style, formatting preferences, recurring goals.
    """
    memory = _get_client().remember(
        content=content, memory_type="preference", tags=["preference", "user"]
    )
    mid = memory.get("id")
    if not mid:
        return f"❌ Failed to store preference: {memory.get('error', 'unknown error')}"
    return f"✅ Stored preference [{mid}]: {content[:100]}"


@tool
def remember_decision(content: str) -> str:
    """Store an important conclusion or decision."""
    memory = _get_client().remember(
        content=content, memory_type="decision", tags=["decision"]
    )
    mid = memory.get("id")
    if not mid:
        return f"❌ Failed to store decision: {memory.get('error', 'unknown error')}"
    return f"✅ Stored decision [{mid}]: {content[:100]}"


@tool
def recall_memory(query: str, limit: int = 5) -> str:
    """
    Retrieve relevant long-term memories.
    Use when the user references previous work or additional context is needed.
    """
    results = _get_client().recall(query=query, limit=limit)
    if not results:
        return "📭 No relevant memories found."
    lines = [f"  [{r.get('id', '?')}] {r.get('content', '')[:150]}" for r in results]
    return "📚 Retrieved memories:\n" + "\n".join(lines)


@tool
def recall_preferences(query: str) -> str:
    """Retrieve stored user preferences."""
    results = _get_client().recall(query=query, limit=5, memory_type="preference")
    if not results:
        return "No stored preferences found."
    return "👤 User preferences:\n" + "\n".join(
        f"  • {r.get('content', '')}" for r in results
    )


@tool
def answer_from_memory(question: str) -> str:
    """Generate a memory-grounded answer using stored memories."""
    answer = _get_client().answer(question)
    return (
        f"🧠 Memory-grounded answer: {answer}"
        if answer
        else "No memory-grounded answer generated."
    )


@tool
def correct_memory(old_content: str, new_content: str) -> str:
    """
    Store a corrected version of outdated information.
    The old fact is preserved in metadata.previous_content for auditability.
    """
    updated = _get_client().correct(old_content=old_content, new_content=new_content)
    mid = updated.get("id")
    if not mid:
        return f"❌ Failed to store correction: {updated.get('error', 'unknown error')}"
    return (
        f"🔄 Correction stored [{mid}]\n"
        f"New fact: {new_content[:120]}\n"
        f"Previous fact preserved in metadata.previous_content"
    )


MEMANTO_TOOLS = [
    remember_fact,
    remember_preference,
    remember_decision,
    recall_memory,
    recall_preferences,
    answer_from_memory,
    correct_memory,
]
