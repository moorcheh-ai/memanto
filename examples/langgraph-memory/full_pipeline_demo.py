import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from integrations.langgraph.memanto_langgraph import MemantoStore, MemantoState, MemoryItem

# Configuration
AGENT_ID = "architect_agent_001"
SESSION_ID = "session_cross_process_test"
API_KEY = os.getenv("MEMANTO_API_KEY", "default_key")

# Initialize Memanto Store
store = MemantoStore(api_key=API_KEY)

@tool
def save_to_memanto(content: str, key: str):
    """Saves important information to the long-term memory store."""
    store.put(namespace=AGENT_ID, key=key, value=content)
    return f"Stored {key} in memory."

@tool
def recall_from_memanto(query: str):
    """Retrieves relevant information from long-term memory."""
    memories = store.search(namespace=AGENT_ID, query=query)
    if not memories:
        return "No relevant memories found."
    return "\n".join([m.content for m in memories])

def call_model(state: MemantoState):
    # This simulates a node that decides to recall or save
    last_message = state["messages"][-1].content
    
    # Logic: If user asks "What do I like?", recall. If user says "I like X", save.
    if "like" in last_message.lower() and "?" in last_message:
        memory_content = recall_from_memanto.invoke(last_message)
        return {"messages": [f"Memory Recall: {memory_content}"]}
    elif "like" in last_message.lower() and "I" in last_message:
        save_to_memanto.invoke({"content": last_message, "key": "user_preference"})
        return {"messages": ["I've noted that in your long-term memory."]}
    
    return {"messages": ["I'm listening."]}

# Build Graph
workflow = StateGraph(MemantoState)
workflow.add_node("agent", call_model)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)
app = workflow.compile()

def run_pipeline(user_input: str):
    inputs = {
        "messages": [user_input], 
        "agent_id": AGENT_ID, 
        "session_id": SESSION_ID, 
        "context_window": []
    }
    result = app.invoke(inputs)
    print(f"Input: {user_input} -> Output: {result['messages'][-1]}")

if __name__ == "__main__":
    print("--- Phase 1: Ingestion (Process 1) ---")
    run_pipeline("I like deep-sea exploration.")
    
    print("\n--- Phase 2: Recall (Simulated Process 2) ---")
    # In a real scenario, this would be a separate execution of the script
    run_pipeline("What do I like?")
