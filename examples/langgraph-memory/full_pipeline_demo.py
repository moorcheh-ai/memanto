import os
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph import MemantoStore
from typing import TypedDict

class AgentState(TypedDict):
    user_id: str
    input: str
    response: str

def memory_node(state: AgentState, config: dict, store: BaseStore):
    user_id = state["user_id"]
    namespace = ("users", user_id)
    
    # Check for existing preferences in MemantoStore
    preference = store.get(namespace, "user_preference")
    
    if preference:
        state["response"] = f"I remember you prefer {preference}. Processing: {state['input']}"
    else:
        state["response"] = f"I don't know your preferences yet. Processing: {state['input']}"
    
    return state

# Build Graph
builder = StateGraph(AgentState)
builder.add_node("memory_node", memory_node)
builder.add_edge(START, "memory_node")
builder.add_edge("memory_node", END)

# Dependency Injection
sdk_client = SdkClient(api_key=os.getenv("MEMANTO_API_KEY", "test_key"))
memanto_store = MemantoStore(sdk_client=sdk_client)

graph = builder.compile(store=memanto_store)

def run_demo():
    user_id = "user_123"
    namespace = ("users", user_id)

    print("--- Session 1: Ingesting Memory ---")
    # Manually put memory into store to simulate previous interaction
    memanto_store.put(namespace, "user_preference", "Dark Mode")
    
    config = {"configurable": {"thread_id": "thread_1"}}
    res1 = graph.invoke({"user_id": user_id, "input": "Hello!"}, config)
    print(f"Session 1 Response: {res1['response']}")

    print("\n--- Session 2: Cross-Thread Recall ---")
    # Different thread, same user_id -> Should recall "Dark Mode" from MemantoStore
    config2 = {"configurable": {"thread_id": "thread_2"}}
    res2 = graph.invoke({"user_id": user_id, "input": "Hi again!"}, config2)
    print(f"Session 2 Response: {res2['response']}")

if __name__ == "__main__":
    run_demo()
