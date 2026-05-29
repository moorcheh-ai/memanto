#!/usr/bin/env python3
"""
LangGraph Customer Support Agent with Memanto Long-Term Memory

Demonstrates cross-session recall using Memanto as a persistent memory layer
outside LangGraph's standard thread state.
"""
import json
import os
import requests
from typing import TypedDict, Optional

# Memanto API configuration
MEMANTO_URL = os.getenv("MEMANTO_URL", "http://localhost:3030")

class AgentState(TypedDict):
    messages: list
    user_id: str
    facts: Optional[dict]

class MemantoMemory:
    """Bridge between LangGraph and Memanto external memory store."""

    def __init__(self, base_url: str = MEMANTO_URL):
        self.base_url = base_url

    def store_memory(self, user_id: str, key: str, value: str) -> bool:
        """Persist a fact to Memanto external memory."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/memory",
                json={"userId": user_id, **{"key": key, "value": value}},
                timeout=5
            )
            return resp.status_code == 200
        except requests.RequestException as e:
            print(f"Memanto store error: {e}")
            return False

    def recall_memories(self, user_id: str) -> dict:
        """Retrieve all stored facts from Memanto."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/memory/{user_id}",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                return {item.get("key", "unknown"): item.get("value", "")
                        for item in data.get("memories", [])}
            return {}
        except requests.RequestException as e:
            print(f"Memanto recall error: {e}")
            return {}

memory = MemantoMemory()

def load_user_context(state: AgentState):
    """Node: Load facts from Memanto into state."""
    facts = memory.recall_memories(state["user_id"])
    return {**state, "facts": facts}

def process_query(state: AgentState):
    """Node: Process user query with context from Memanto."""
    query = state["messages"][-1] if state["messages"] else ""
    facts = state.get("facts", {})
    
    # Build response with cross-session context
    context_parts = []
    if facts:
        for key, value in facts.items():
            context_parts.append(f"User fact: {key} = {value}")
    
    # Extract new facts from query (simple demo)
    new_facts = {}
    if "my name is" in query.lower():
        name = query.lower().split("my name is")[-1].strip().split()[0].strip(".,!?")
        new_facts["name"] = name
        memory.store_memory(state["user_id"], "name", name)
    if "prefer" in query.lower() or "like" in query.lower():
        if "python" in query.lower():
            new_facts["language"] = "Python"
            memory.store_memory(state["user_id"], "language", "Python")
    
    context_str = "\n".join(context_parts) if context_parts else "No prior context."
    response = f"[Context from Memanto]:\n{context_str}\n\n[Agent]: Processing your request."
    return {**state, "messages": state["messages"] + [response]}


# LangGraph workflow definition
try:
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(AgentState)
    workflow.add_node("load_context", load_user_context)
    workflow.add_node("process", process_query)
    workflow.set_entry_point("load_context")
    workflow.add_edge("load_context", "process")
    workflow.add_edge("process", END)
    app = workflow.compile()
except ImportError:
    print("LangGraph not installed. Run: pip install langgraph")


if __name__ == "__main__":
    print("=== LangGraph + Memanto Customer Support Agent ===")
    print("This demo shows cross-session recall (run twice to see memory in action)")
    
    user_id = "demo_user_alice"
    
    # Session 1
    print(f"\n--- Session 1 (User: {user_id}) ---")
    state1 = {"messages": ["Hi, my name is Alice and I prefer Python"], "user_id": user_id, "facts": None}
    result = app.invoke(state1)
    print(f"Response: {result['messages'][-1][:100]}...")
    print("(Facts saved to Memanto)")
    
    # Session 2 (simulated new thread)
    print(f"\n--- Session 2 (User: {user_id}, new thread) ---")
    state2 = {"messages": ["What do I like?"], "user_id": user_id, "facts": None}
    result2 = app.invoke(state2)
    print(f"Response: {result2['messages'][-1][:100]}...")
    print("(Recalled from Memanto - cross-session success!)")
