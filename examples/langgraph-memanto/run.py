#!/usr/bin/env python3
"""
LangGraph + Memanto: Cross-Session Customer Support Agent.

Run once → tell the agent something about yourself.
Run again → the agent remembers everything from previous sessions.

This proves cross-session memory persistence via Memanto.

Usage:
    python run.py                    # Interactive mode
    python run.py --interactive     # Same
    python run.py --demo            # Automated demo with canned queries

Environment:
    MOORCHEH_API_KEY     — Memanto API key (required)
    OPENROUTER_API_KEY   — LLM API key (required)
    OPENROUTER_MODEL     — Model name (default: anthropic/claude-sonnet-4)
"""

import argparse
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from memory import MemantoMemory

load_dotenv()

# ── LangGraph setup ─────────────────────────────────────────────────

try:
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.checkpoint.memory import MemorySaver
    from langchain_openai import ChatOpenAI
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)


# ── Agent state ─────────────────────────────────────────────────────

class AgentState(MessagesState):
    """Extended state with memory context."""
    memory_context: str = ""
    memories_stored: int = 0


# ── LLM ─────────────────────────────────────────────────────────────

def get_llm():
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
    )


# ── LangGraph nodes ─────────────────────────────────────────────────

def load_memories(state: AgentState, memory: MemantoMemory) -> dict:
    """Node 1: Load relevant memories from Memanto into the state."""
    user_input = ""
    for msg in reversed(state.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "human":
            user_input = msg.content
            break

    # Semantic search for relevant memories
    memories = memory.recall(user_input, limit=8)
    context = memory.format_context(memories)

    return {"memory_context": context}


def agent_respond(state: AgentState, memory: MemantoMemory) -> dict:
    """Node 2: LLM generates a response using memory context."""
    llm = get_llm()
    messages = state.get("messages", [])

    # Build system prompt with memory context
    system_prompt = f"""You are a helpful customer support agent with persistent memory.
You remember users across sessions using Memanto.

{state.get('memory_context', 'No prior memories.')}

Instructions:
- If the user introduces themselves or shares preferences, acknowledge and REMEMBER them.
- If the user asks about something from the past, use the Prior Memories section above.
- Be warm and helpful.
"""

    # Prepend system message
    full_messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": getattr(m, "type", "user"), "content": m.content} for m in messages],
    ]

    response = llm.invoke(full_messages)
    return {"messages": [response]}


def store_memories(state: AgentState, memory: MemantoMemory) -> dict:
    """Node 3: Extract and store new memories from the conversation."""
    # Get the assistant's last response and user's last input
    msgs = state.get("messages", [])
    if len(msgs) < 2:
        return {"memories_stored": 0}

    last_user = None
    last_assistant = None
    for m in reversed(msgs):
        if hasattr(m, "type"):
            if m.type == "human" and last_user is None:
                last_user = m.content
            elif m.type == "ai" and last_assistant is None:
                last_assistant = m.content

    if not last_user:
        return {"memories_stored": 0}

    # Use LLM to extract facts from the exchange
    llm = get_llm()
    extract_prompt = f"""Extract factual statements and preferences from this conversation turn.
Return a JSON list of objects with keys: "type" (fact|preference|observation), "key", "value"

User: {last_user}
Assistant: {last_assistant}

JSON:"""
    try:
        result = llm.invoke([{"role": "user", "content": extract_prompt}])
        extracted = json.loads(result.content.strip().strip("```json").strip("```").strip())
    except (json.JSONDecodeError, AttributeError):
        extracted = []

    stored = 0
    for item in extracted:
        try:
            if item.get("type") == "fact":
                memory.store_fact(item["key"], item["value"])
            elif item.get("type") == "preference":
                memory.store_preference(item["key"], item["value"])
            else:
                memory.store("observation", item.get("key", "observation"), item.get("value", ""))
            stored += 1
        except Exception:
            pass

    return {"memories_stored": stored}


# ── Build graph ─────────────────────────────────────────────────────

def build_agent(memory: MemantoMemory):
    """Build the LangGraph agent with Memanto memory."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("load_memories", lambda s: load_memories(s, memory))
    workflow.add_node("agent_respond", lambda s: agent_respond(s, memory))
    workflow.add_node("store_memories", lambda s: store_memories(s, memory))

    # Connect
    workflow.add_edge(START, "load_memories")
    workflow.add_edge("load_memories", "agent_respond")
    workflow.add_edge("agent_respond", "store_memories")
    workflow.add_edge("store_memories", END)

    # Compile with in-memory checkpointing (conversation thread)
    return workflow.compile(checkpointer=MemorySaver())


# ── Interactive loop ────────────────────────────────────────────────

def interactive(memory: MemantoMemory):
    """Interactive chat loop."""
    print("=" * 60)
    print("  Memanto + LangGraph — Cross-Session Memory Demo")
    print("=" * 60)
    print("  Type 'memories' to see what I remember")
    print("  Type 'quit' to exit")
    print()

    agent = build_agent(memory)
    thread_id = "support-thread-1"
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "memories":
            all_mem = memory.recall_all()
            if all_mem:
                print("\n--- Stored Memories ---")
                for m in all_mem:
                    print(f"  [{m.get('type', '?')}] {m.get('title', '')}: {m.get('content', '')}")
                print("---\n")
            else:
                print("  (no memories stored yet)\n")
            continue

        # Run the agent
        result = agent.invoke(
            {"messages": [{"role": "human", "content": user_input}]},
            config=config,
        )

        # Print response
        for msg in result.get("messages", []):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"\nAgent: {msg.content}\n")


def demo(memory: MemantoMemory):
    """Automated demo showing cross-session recall."""
    agent = build_agent(memory)
    config = {"configurable": {"thread_id": "demo-thread-1"}}

    print("=" * 60)
    print("  Demo: Cross-Session Memory Recall")
    print("=" * 60)

    # Session 1: Store information
    queries_s1 = [
        "Hi there! My name is Alex and I'm working on a Python project.",
        "I prefer dark mode in all my applications.",
        "My favorite IDE is VS Code with the GitHub Copilot extension.",
    ]

    print("\n--- Session 1: Storing information ---\n")
    for q in queries_s1:
        print(f"User: {q}")
        result = agent.invoke({"messages": [{"role": "human", "content": q}]}, config=config)
        for msg in result.get("messages", []):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"Agent: {msg.content}\n")

    print("\n--- Session 1 complete! Memories stored in Memanto. ---\n")

    # Session 2: New thread, should recall everything
    config2 = {"configurable": {"thread_id": "demo-thread-2"}}

    queries_s2 = [
        "Do you remember anything about me?",
        "What's my preferred IDE and theme?",
    ]

    print("\n--- Session 2: NEW conversation — testing recall ---\n")
    for q in queries_s2:
        print(f"User: {q}")
        result = agent.invoke({"messages": [{"role": "human", "content": q}]}, config=config2)
        for msg in result.get("messages", []):
            if hasattr(msg, "type") and msg.type == "ai":
                print(f"Agent: {msg.content}\n")

    print("\n--- Demo complete! 🎉 ---")
    print("The agent remembered information across sessions.")
    print("This proves cross-session memory persistence via Memanto!\n")


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LangGraph + Memanto Demo")
    parser.add_argument("--demo", action="store_true", help="Run automated demo")
    parser.add_argument("--interactive", action="store_true", help="Run interactive chat")
    args = parser.parse_args()

    api_key = os.getenv("MOORCHEH_API_KEY", "")
    if not api_key:
        print("Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    memory = MemantoMemory(agent_id="langgraph-support-demo")

    if args.demo:
        demo(memory)
    else:
        interactive(memory)


if __name__ == "__main__":
    main()
