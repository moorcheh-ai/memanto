"""
Memanto + LangGraph Integration Example
========================================
AI Customer Support Agent with Cross-Session Memory

Demonstrates a LangGraph workflow using Memanto to store and
retrieve memories across sessions. The agent remembers customer
details from "yesterday" that aren't in the current state.
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from memanto import MemantoClient
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from typing import Dict, Any, Optional

load_dotenv()

MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "")
MEMANTO_NAMESPACE = os.getenv("MEMANTO_NAMESPACE", "langgraph-support")

memanto = MemantoClient(
    api_key=MEMANTO_API_KEY,
    namespace=MEMANTO_NAMESPACE,
)

class AgentState(TypedDict):
    customer_id: str
    customer_name: str
    query: str
    context: Optional[str]
    response: Optional[str]
    session_id: Optional[str]

def load_memories(state: AgentState) -> Dict:
    """Cross-session recall: load memories from Memanto."""
    customer_id = state["customer_id"]
    name = state.get("customer_name", customer_id)
    
    memories = memanto.recall(query=f"What do I know about {name}?", limit=5)
    prefs = memanto.recall(query=f"{name} preferences", memory_type="preference")
    issues = memanto.recall(query=f"{name} past support issues", memory_type="fact")
    
    parts = []
    if memories: parts.append(f"Memories: {memories}")
    if prefs: parts.append(f"Preferences: {prefs}")
    if issues: parts.append(f"Past issues: {issues}")
    
    context = "\\n".join(parts) if parts else "No prior memories found."
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {"context": context, "session_id": session_id}

def process_query(state: AgentState) -> Dict:
    """Use Memanto answer() with memory context."""
    response = memanto.answer(
        query=state["query"],
        context=state.get("context", ""),
        instructions="You are a customer support agent. Personalize responses using stored memories."
    )
    return {"response": response}

def store_memories(state: AgentState) -> Dict:
    """Store interaction as memory for future sessions."""
    memanto.remember(
        content=f"{state['customer_name']} asked: {state['query']}",
        memory_type="fact",
        tags=["support", state["customer_id"]],
    )
    return {}

workflow = StateGraph(AgentState)
workflow.add_node("load_memories", load_memories)
workflow.add_node("process_query", process_query)
workflow.add_node("store_memories", store_memories)
workflow.set_entry_point("load_memories")
workflow.add_edge("load_memories", "process_query")
workflow.add_edge("process_query", "store_memories")
workflow.add_edge("store_memories", END)

support_graph = workflow.compile()

def main():
    print("\U0001f99e Memanto + LangGraph Support Agent (Cross-Session Memory)")
    print("=" * 55)
    cid = input("Customer ID: ").strip()
    name = input("Your name: ").strip()
    while True:
        q = input(f"\\n\\U0001f4ac {name}: ").strip()
        if q in ("/exit", "/quit"): break
        result = support_graph.invoke({
            "customer_id": cid, "customer_name": name,
            "query": q, "context": None, "response": None, "session_id": None,
        })
        print(f"\\U0001f916 Agent: {result.get('response', 'No response')}")

if __name__ == "__main__":
    main()
