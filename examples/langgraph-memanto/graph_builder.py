"""
LangGraph StateGraph Builder with Memory Nodes.

Builds a LangGraph StateGraph that integrates Memanto as a persistent
long-term memory layer with cross-session recall.

Graph topology:
    recall_memories → agent → store_memories

- recall_memories: Pre-node that recalls relevant memories from Memanto
  and injects them into the LLM context
- agent: The main LLM processing node (placeholder — replace with your own)
- store_memories: Post-node that extracts engineering signals and stores
  them back to Memanto for future sessions

Cross-session recall works because all sessions share the same Memanto
backend. A memory stored in session A will be recalled in session B when
the query is relevant.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from memory_backend import MemoryBackend, get_backend
from memory_nodes import recall_memories, store_memories


# ---------------------------------------------------------------------------
# Graph State Definition
# ---------------------------------------------------------------------------

# We use a plain dict for maximum flexibility with LangGraph.
# The state keys are:
#   - messages: list[dict] — conversation messages
#   - session_id: str — session identifier for cross-session recall
#   - stage: str | None — current workflow stage (research, planning, etc.)
#   - backend: MemoryBackend | None — backend override (injected at runtime)
#   - memory_context: str — formatted memories from recall_memories node
#   - recalled_memories: list[dict] — raw recalled memories
#   - stored_memory_ids: list[str] — IDs of memories stored by store_memories


# ---------------------------------------------------------------------------
# Placeholder Agent Node
# ---------------------------------------------------------------------------

def placeholder_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Placeholder agent node. Replace with your actual LLM call.

    In production, this would call an LLM (OpenAI, Anthropic, etc.)
    with the memory_context injected into the system prompt.

    This placeholder echoes the user's message and the memory context
    for demonstration purposes.
    """
    messages = state.get("messages", [])
    memory_context = state.get("memory_context", "")

    # Build the system message with memory context
    system_content = "You are a helpful assistant."
    if memory_context:
        system_content += f"\n\n{memory_context}"

    # Get the last user message
    user_content = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_content = content
            break

    # Placeholder response (in production, call your LLM here)
    assistant_content = f"[Agent response based on memory context]\nUser asked: {user_content}"
    if memory_context:
        assistant_content += f"\nMemory context was injected ({len(memory_context)} chars)"

    new_messages = list(messages) + [
        {"role": "system", "content": system_content},
        {"role": "assistant", "content": assistant_content},
    ]

    return {
        **state,
        "messages": new_messages,
    }


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_memory_graph(
    agent_node: Any | None = None,
    backend: MemoryBackend | None = None,
) -> StateGraph:
    """Build a LangGraph StateGraph with Memanto memory nodes.

    Args:
        agent_node: Custom agent node function. If None, uses placeholder_agent.
        backend: MemoryBackend instance. If None, uses get_backend() at runtime.

    Returns:
        A compiled LangGraph StateGraph ready for invocation.
    """
    _agent_node = agent_node or placeholder_agent

    # Define the graph
    graph = StateGraph(dict)

    # Add nodes
    graph.add_node("recall_memories", recall_memories)
    graph.add_node("agent", _agent_node)
    graph.add_node("store_memories", store_memories)

    # Define edges: recall → agent → store → END
    graph.set_entry_point("recall_memories")
    graph.add_edge("recall_memories", "agent")
    graph.add_edge("agent", "store_memories")
    graph.add_edge("store_memories", END)

    return graph.compile()


def invoke_graph(
    user_message: str,
    session_id: str = "default",
    stage: str | None = None,
    backend: MemoryBackend | None = None,
    agent_node: Any | None = None,
    existing_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convenience function to invoke the memory-enhanced graph.

    Args:
        user_message: The user's input message.
        session_id: Session identifier for cross-session recall.
        stage: Current workflow stage (e.g., "research", "planning").
        backend: MemoryBackend instance. Uses default if None.
        agent_node: Custom agent function. Uses placeholder if None.
        existing_messages: Prior messages to include in the conversation.

    Returns:
        The final graph state dict after execution.
    """
    _backend = backend or get_backend()
    graph = build_memory_graph(agent_node=agent_node, backend=_backend)

    messages = list(existing_messages or [])
    messages.append({"role": "user", "content": user_message})

    initial_state = {
        "messages": messages,
        "session_id": session_id,
        "stage": stage,
        "backend": _backend,
        "memory_context": "",
        "recalled_memories": [],
        "stored_memory_ids": [],
    }

    result = graph.invoke(initial_state)
    return result
