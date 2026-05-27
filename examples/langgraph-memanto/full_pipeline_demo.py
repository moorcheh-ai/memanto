import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from integrations.langgraph.memanto_manager import MemantoMemoryManager, MemoryType

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    global_goals: list
    current_phase: str

def researcher(state: AgentState):
    # Simulated research logic
    return {"messages": [("assistant", "Research complete: Memanto V3 is type-safe.")], "current_phase": "critic"}

def critic(state: AgentState):
    # Simulated critic logic
    return {"messages": [("assistant", "Critique: Add OCC logic to the checkpointer.")], "current_phase": "writer"}

def writer(state: AgentState):
    # Simulated writer logic
    return {"messages": [("assistant", "Final Report: Implementation of OCC in MemantoBridge finished.")], "current_phase": "end"}

def supervisor(state: AgentState):
    if state["current_phase"] == "critic": return "critic"
    if state["current_phase"] == "writer": return "writer"
    return "researcher"

# Configuration
AGENT_ID = "super_agent_001"
API_KEY = os.getenv("MEMANTO_API_KEY", "test_key")

# Initialize Native Persistence
checkpointer = MemantoCheckpointer(agent_id=AGENT_ID, api_key=API_KEY)
memory_manager = MemantoMemoryManager(agent_id=AGENT_ID, api_key=API_KEY)

# Build Graph
builder = StateGraph(AgentState)
builder.add_node("researcher", researcher)
builder.add_node("critic", critic)
builder.add_node("writer", writer)

builder.set_entry_point("researcher")
builder.add_edge("researcher", "critic")
builder.add_edge("critic", "writer")
builder.add_edge("writer", END)

graph = builder.compile(checkpointer=checkpointer)

def run_cross_session_demo():
    config = {"configurable": {"thread_id": "session_alpha"}}
    
    print("--- Session A: Starting Workflow ---")
    initial_input = {"messages": [("user", "Analyze Memanto V3")], "global_goals": ["Type Safety"], "current_phase": "researcher"}
    for event in graph.stream(initial_input, config):
        print(event)

    print("\n--- System Reboot / Process Restart ---")
    
    print("\n--- Session B: Resuming Workflow ---")
    # No input provided, relying on MemantoCheckpointer to recall state
    for event in graph.stream(None, config):
        print(event)

if __name__ == "__main__":
    run_cross_session_demo()
