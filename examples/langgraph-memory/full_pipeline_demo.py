import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph.memanto_store import MemantoStore

# Type-safe state definition
class AgentState(TypedDict):
    input: str
    response: str
    user_id: str

def memory_node(state: AgentState, config: dict, store: MemantoStore):
    user_id = state["user_id"]
    user_input = state["input"]
    namespace = ("users", user_id)
    
    # Semantic recall across sessions
    past_memories = store.search(namespace, user_input)
    
    # Store current interaction for future sessions
    store.put(namespace, "last_interaction", user_input)
    
    context = f"Past context: {past_memories}" if past_memories else "No past context."
    return {"response": f"Processed input: {user_input} | {context}"}

def run_demo():
    # Initialize SDK and generic Store
    sdk = SdkClient()
    memanto_store = MemantoStore(sdk)
    checkpointer = MemorySaver()
    
    # Build Graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", memory_node)
    workflow.add_edge(START, "agent")
    workflow.add_edge("agent", END)
    
    app = workflow.compile(checkpointer=checkpointer, store=memanto_store)
    
    # Session 1: Ingest memory
    user_id = "user_123"
    config_1 = {"configurable": {"thread_id": "session_1"}}
    app.invoke(
        {"input": "I prefer my reports in Markdown format.", "user_id": user_id}, 
        config=config_1
    )
    print("Session 1: Memory stored.")

    # Session 2: Recall memory in a different thread/process simulation
    config_2 = {"configurable": {"thread_id": "session_2"}}
    result = app.invoke(
        {"input": "How should I format my reports?", "user_id": user_id}, 
        config=config_2
    )
    
    print(f"Session 2 Response: {result['response']}")
    assert "Markdown" in result['response']
    print("Cross-session persistence verified.")

if __name__ == "__main__":
    run_demo()
