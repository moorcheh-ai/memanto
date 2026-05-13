"""LangGraph nodes for the Memanto-powered agent.

Each node is a pure function that takes the current AgentState
and returns an updated AgentState.
"""

from __future__ import annotations

import json
from typing import Any

from langgraph_memanto.memory_client import MemantoClient
from langgraph_memanto.state import AgentState

# ---------------------------------------------------------------------------
# System prompt that tells the LLM how to use Memanto memory
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a helpful customer support agent with a "permanent brain" — \
you can store and recall memories across conversations using Memanto.

Whenever you learn something important about the user, call:
  REMEMBER(<type>, "<title>", "<content>")
  where type is one of: fact, preference, goal, decision, event, observation

When the user asks something that might reference past conversations, call:
  RECALL("<query>")

Guidelines:
- Keep memories concise and factual
- Use the 'fact' type for verified information
- Use 'preference' for user likes/dislikes
- Use 'observation' for behavioral patterns
- Reference past memories when answering questions
"""


def think_node(state: AgentState, llm_model: str = "gpt-4o-mini") -> dict[str, Any]:
    """Think node: the LLM processes user input and decides what to do.

    This simulates the "thinking" step of an agent loop. In production,
    replace this with an actual LLM call.
    """
    user_input = state.user_input

    # Build a prompt that includes any retrieved memories
    memory_context = ""
    if state.retrieved_memories:
        memory_context = "\nRetrieved from long-term memory:\n"
        for mem in state.retrieved_memories[:5]:
            title = mem.get("title", mem.get("text", "")[:80])
            content = mem.get("content", mem.get("text", ""))[:200]
            mem_type = mem.get("memory_type", mem.get("type", "unknown"))
            memory_context += f"  [{mem_type}] {title}: {content}\n"

    prompt = f"""{SYSTEM_PROMPT}

{memory_context}

User: {user_input}

First, think about whether you need to:
1. Remember any new information (facts, preferences, etc.)
2. Recall past information to answer the question
3. Just respond directly

Show your reasoning and any REMEMBER/RECALL calls needed:"""

    # Simulate LLM thinking (in production, call the actual LLM)
    thoughts = _simulate_thinking(user_input, state)

    return {"thoughts": thoughts}


def _simulate_thinking(user_input: str, state: AgentState) -> str:
    """Simulate LLM reasoning about what to remember or recall.

    In production, replace this with an actual LLM call.
    This simulation provides realistic examples for the demo.
    """
    user_lower = user_input.lower()

    # Pattern matching for common support scenarios
    if any(word in user_lower for word in ["remember", "save", "store", "my name", "i am", "my email"]):
        return (
            f"I need to remember this user information.\n"
            f"REMEMBER(fact, \"User information\", \"{user_input}\")\n"
            f"Then respond confirming the information was saved."
        )
    elif any(word in user_lower for word in ["recall", "remember", "what did", "last time", "previously", "before"]):
        return (
            f"The user is asking about past interactions.\n"
            f"RECALL(\"{user_input}\")\n"
            f"I need to search my long-term memory to answer this."
        )
    elif any(word in user_lower for word in ["prefer", "like", "love", "want", "need", "wish"]):
        return (
            f"The user is expressing a preference.\n"
            f"REMEMBER(preference, \"User preference\", \"{user_input}\")\n"
            f"I should also check if I already know their preferences.\n"
            f"RECALL(\"user preferences\")\n"
            f"Then respond appropriately."
        )
    elif any(word in user_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon"]):
        return (
            f"User is greeting me. Let me check if I know them.\n"
            f"RECALL(\"greeting recent conversation\")\n"
            f"I'll respond with appropriate context from past interactions."
        )
    else:
        return (
            f"General query. Let me check my memories for relevant context.\n"
            f"RECALL(\"{user_input}\")\n"
            f"Then craft a helpful response."
        )


def memory_node(state: AgentState, client: MemantoClient) -> dict[str, Any]:
    """Memory node: execute remember/recall operations via Memanto.

    Parses the thoughts from the think node and performs the
    appropriate Memanto operations.
    """
    thoughts = state.thoughts or ""
    memory_ops: list[dict[str, str]] = []
    retrieved: list[dict[str, Any]] = []

    # Parse REMEMBER instructions
    import re

    remember_matches = re.findall(
        r"REMEMBER\((\w+),\s*\"([^\"]+)\",\s*\"([^\"]+)\"\)",
        thoughts,
    )
    for mem_type, title, content in remember_matches:
        result = client.remember(
            memory_type=mem_type.lower(),
            title=title[:100],
            content=content[:10000],
        )
        memory_ops.append({
            "op": "remember",
            "type": mem_type,
            "title": title,
            "status": "ok" if "error" not in result else "error",
        })

    # Parse RECALL instructions
    recall_matches = re.findall(r"RECALL\(\"([^\"]+)\"\)", thoughts)
    for query in recall_matches:
        results = client.recall(query=query, limit=5)
        if results:
            retrieved.extend(results)
            memory_ops.append({
                "op": "recall",
                "query": query,
                "count": str(len(results)),
                "status": "ok",
            })
        else:
            memory_ops.append({
                "op": "recall",
                "query": query,
                "count": "0",
                "status": "no_results",
            })

    # If no explicit instructions, try recall on the user's input
    if not remember_matches and not recall_matches and state.user_input:
        results = client.recall(query=state.user_input, limit=3)
        if results:
            retrieved.extend(results)

    return {
        "memory_ops": memory_ops,
        "retrieved_memories": retrieved,
    }


def respond_node(state: AgentState, llm_model: str = "gpt-4o-mini") -> dict[str, Any]:
    """Respond node: generate the final user-facing response.

    In production, this would call an LLM with the full context
    (user input, retrieved memories, memory ops). For the demo,
    we generate a simulated response.
    """
    user_input = state.user_input
    ops = state.memory_ops
    memories = state.retrieved_memories

    # Build context from memory operations
    ops_summary = ""
    for op in ops:
        if op["op"] == "remember":
            ops_summary += f"✓ Saved: [{op['type']}] {op['title']}\n"
        elif op["op"] == "recall":
            count = int(op.get("count", 0))
            if count > 0:
                ops_summary += f"✓ Found {count} relevant memory/memories for '{op['query']}'\n"
            else:
                ops_summary += f"ℹ No memories found for '{op['query']}'\n"

    memory_summary = ""
    if memories:
        memory_summary = "\nRelevant memories:\n"
        for m in memories[:3]:
            memory_summary += (
                f"  • {m.get('title', '')}: {m.get('content', '')[:150]}\n"
            )

    response = _generate_response(user_input, ops_summary, memory_summary)

    return {"response": response}


def _generate_response(user_input: str, ops_summary: str, memory_summary: str) -> str:
    """Generate a simulated response. Replace with LLM call in production."""
    user_lower = user_input.lower()

    if ops_summary:
        context_line = f"\n\n{ops_summary}"
    elif memory_summary:
        context_line = f"\n\n{memory_summary}"
    else:
        context_line = ""

    if any(w in user_lower for w in ["hello", "hi", "hey"]):
        return f"Hello! I'm your customer support agent. How can I help you today?{context_line}"
    elif "remember" in user_lower or "save" in user_lower:
        return f"I've saved that information to my long-term memory. I'll remember it for future conversations!{context_line}"
    elif "recall" in user_lower or "what did" in user_lower:
        if memory_summary:
            return f"Here's what I remember from our past conversations:{memory_summary}{context_line}"
        else:
            return f"I don't have any specific memories about that yet. Let me know what you'd like me to remember!{context_line}"
    elif "prefer" in user_lower or "like" in user_lower:
        return f"Thanks for telling me! I've noted your preferences in my long-term memory so I can tailor future responses.{context_line}"
    else:
        return f"Thanks for reaching out! I've checked my long-term memory for relevant context.{context_line}\n\nLet me know how I can assist you further!"
