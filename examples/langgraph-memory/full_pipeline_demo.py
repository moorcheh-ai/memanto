import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph import MemantoStore

# Define a simple state for the graph
class AgentState(TypedDict):
    user_input: str
    response: str

# Define the Item Type for the store (e.g., storing strings for preferences)
class UserPreference(TypedDict):
    preference: str

def memory_node(state: AgentState, config: dict, store: MemantoStore[str]):
    # Extract user identity from config
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    namespace = ("users", user_id)
    
    # Try to recall existing preference
    preference = store.get(namespace, "theme_preference")
    
    if "I like" in state["user_input"]:
        # Extract and store new preference
        pref_value = state["user_input"].split("I like ")[1]
        store.put(namespace, "theme_preference", pref_value)
        return {"response": f"Noted! I'll remember that you like {pref_value}."}
    
    if preference:
        return {"response": f"I remember you like {preference}!"}
    
    return {"response": "I don't know your preferences yet."}

def create_graph():
    builder = StateGraph(AgentState)
    builder.add_node("memory_node", memory_node)
    builder.add_edge(START, "memory_node")
    builder.add_edge("memory_node", END)
    return builder.compile()

def run_demo():
    # Initialize SDK Client
    sdk = SdkClient(api_key=os.getenv("MEMANTO_API_KEY", "test_key"))
    
    # Create the Generic Store for strings
    store = MemantoStore[str](sdk_client=sdk, item_type=str)
    
    user_id = "architect_user_001"
    config = {"configurable": {"user_id": user_id}}
    
    # SESSION 1: Ingestion
    print("--- Session 1: Ingesting Preference ---")
    graph_1 = create_graph()
    input_1 = {"user_input": "I like Dark Mode"}
    res_1 = graph_1.invoke(input_1, config=config, store=store)
    print(f"Agent: {res_1['response']}")
    
    # SESSION 2: Cross-Process/Instance Recall
    # Re-instantiating everything to simulate a new process/session
    print("\n--- Session 2: Recalling Preference (New Instance) ---")
    sdk_new = SdkClient(api_key=os.getenv("MEMANTO_API_KEY", "test_key"))
    store_new = MemantoStore[str](sdk_client=sdk_new, item_type=str)
    graph_2 = create_graph()
    
    input_2 = {"user_input": "What do I like?"}
    res_2 = graph_2.invoke(input_2, config=config, store=store_new)
    print(f"Agent: {res_2['response']}")

if __name__ == "__main__":
    run_demo()
