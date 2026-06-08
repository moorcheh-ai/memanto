import os
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph import MemantoStore

class UserPreference(BaseModel):
    theme: str = Field(description="User preferred UI theme")
    language: str = Field(description="User preferred language")

class AgentState(BaseModel):
    user_id: str
    query: str
    response: str = ""

def memory_node(state: AgentState, config: dict, store: BaseStore):
    # Namespace uses user_id as AGENT_ID
    namespace = (state.user_id, "preferences")
    key = "settings"
    
    prefs = store.get(namespace, key)
    if not prefs:
        # Initializing default memory if absent
        prefs = UserPreference(theme="dark", language="en")
        store.put(namespace, key, prefs)
    
    state.response = f"Hello! I see you prefer {prefs.language} and {prefs.theme} mode."
    return state

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("memory_node", memory_node)
    workflow.add_edge(START, "memory_node")
    workflow.add_edge("memory_node", END)
    return workflow

def run_session(user_id: str, query: str, store: BaseStore):
    graph = create_graph().compile(store=store)
    inputs = {"user_id": user_id, "query": query}
    result = graph.invoke(inputs)
    print(f"User: {user_id} | Response: {result['response']}")

if __name__ == "__main__":
    # Initialize Memanto SDK Client
    client = SdkClient()
    
    # Instantiate type-safe MemantoStore with UserPreference schema
    memanto_store = MemantoStore(client=client, schema=UserPreference)
    
    # Session 1: Create persistence
    print("--- Session 1 ---")
    run_session("user_123", "What are my settings?", memanto_store)
    
    # Modify memory manually to prove persistence
    memanto_store.put(("user_123", "preferences"), "settings", UserPreference(theme="light", language="fr"))
    
    # Session 2: Recall persistence across processes/invocations
    print("\n--- Session 2 ---")
    run_session("user_123", "What are my settings now?", memanto_store)
