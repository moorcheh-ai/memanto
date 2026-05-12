"""
LangGraph Customer Support Agent with Memanto long-term memory.

Demonstrates cross-session recall: the agent remembers user preferences,
past issues, and facts from previous sessions that are not in the current
LangGraph state.

Flow:
  1. User sends a message
  2. Agent retrieves relevant memories from Memanto (cross-session context)
  3. Agent generates a response using the context + current conversation
  4. New facts/preferences are stored back to Memanto
"""

import json
import os
from typing import Any, Literal

from memanto_memory import MemantoMemory

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint import MemorySaver
except ImportError:
    raise ImportError("Install langgraph: pip install langgraph")


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"


class AgentState(dict):
    messages: list[dict[str, str]]
    user_id: str
    cross_session_context: str
    new_memories: list[dict[str, Any]]


memory_store = MemantoMemory()


def retrieve_memories(state: AgentState) -> AgentState:
    """Retrieve relevant memories from Memanto for cross-session context."""
    user_id = state.get("user_id", "default")
    query = state["messages"][-1]["content"] if state["messages"] else ""
    memories = memory_store.search_memories(query=query, scope_id=user_id, limit=8)
    recent = memory_store.get_cross_session_context(user_id)
    state["cross_session_context"] = recent
    return state


def call_llm(state: AgentState) -> AgentState:
    """Call Claude API with conversation history + cross-session memories."""
    import urllib.request

    messages = state.get("messages", [])
    context = state.get("cross_session_context", "")
    user_id = state.get("user_id", "default")

    system_prompt = "You are a helpful customer support agent."
    if context:
        system_prompt += (
            "\n\nYou have the following memories from past interactions with this user:\n"
            + context
        )

    body = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": messages,
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            reply = data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        reply = f"Sorry, I encountered an error: {e}"

    state["messages"] = messages + [{"role": "assistant", "content": reply}]
    return state


def extract_memories(state: AgentState) -> AgentState:
    """Extract facts and preferences from the conversation and store to Memanto."""
    user_id = state.get("user_id", "default")
    conversation = state.get("messages", [])
    last_user_msg = ""
    last_assistant_msg = ""
    for msg in reversed(conversation):
        if msg["role"] == "user" and not last_user_msg:
            last_user_msg = msg["content"]
        if msg["role"] == "assistant" and not last_assistant_msg:
            last_assistant_msg = msg["content"]
        if last_user_msg and last_assistant_msg:
            break

    if "my name is" in last_user_msg.lower():
        name = last_user_msg.lower().split("my name is")[-1].strip().split()[0]
        memory_store.store_memory(
            memory_type="fact",
            title=f"User's name is {name}",
            content=f"The user introduced themselves as {name}.",
            scope_id=user_id,
            tags=["user_name", "identity"],
        )

    if "prefer" in last_user_msg.lower() or "like" in last_user_msg.lower():
        memory_store.store_memory(
            memory_type="preference",
            title="User expressed a preference",
            content=last_user_msg[:500],
            scope_id=user_id,
            tags=["preference"],
            confidence=0.7,
        )

    return state


def should_continue(state: AgentState) -> Literal["extract_memories", "end"]:
    return "extract_memories" if state.get("messages") else "end"


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve_memories", retrieve_memories)
    workflow.add_node("call_llm", call_llm)
    workflow.add_node("extract_memories", extract_memories)

    workflow.set_entry_point("retrieve_memories")
    workflow.add_edge("retrieve_memories", "call_llm")
    workflow.add_conditional_edges("call_llm", should_continue)
    workflow.add_edge("extract_memories", END)

    return workflow


def run_agent(user_id: str, message: str) -> str:
    graph = build_graph()
    app = graph.compile()

    initial_state: AgentState = {
        "messages": [{"role": "user", "content": message}],
        "user_id": user_id,
        "cross_session_context": "",
        "new_memories": [],
    }

    result = app.invoke(initial_state)
    messages = result.get("messages", [])
    return messages[-1]["content"] if messages else ""


if __name__ == "__main__":
    import sys

    uid = sys.argv[1] if len(sys.argv) > 1 else "alice"
    msg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hello! What can you help me with?"

    print(f"User ({uid}): {msg}")
    print(f"Agent: {run_agent(uid, msg)}")
