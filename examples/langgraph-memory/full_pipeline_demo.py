import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph import MemantoStore

# Define State
class AgentState(TypedDict):
    user_input: str
    memory_context: str
    response: str

# Define Nodes
def recall_node(state: AgentState, config: dict, store: MemantoStore):
    user_id = config["configurable"].get("user_id", "user_123")
    # Search semantic memory using the Store abstraction
    memories = store.search(namespace=(user_id,), query=state["user_input"])
    context = " ".join([str(m) for m in memories]) if memories else "No relevant memory found."
    return {"memory_context": context}

def process_node(state: AgentState):
    # Logic simulating agent processing with memory
    response = f"Processed '{state['user_input']}' using context: {state['memory_context']}"
    return {"response": response}

def store_node(state: AgentState, config: dict, store: MemantoStore):
    user_id = config["configurable"].get("user_id", "user_123")
    # Persist new fact into long-term memory
    store.put(namespace=(user_id,), key="user_preference", value=state["user_input"])
    return {"response": "Memory saved."}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("recall", recall_node)
workflow.add_node("process", process_node)
workflow.add_node("store", store_node)

workflow.add_edge(START, "recall")
workflow.add_edge("recall", "process")
workflow.add_edge("process", "store")
workflow.add_edge("store", END)

# Setup SDK and Store
sdk_client = SdkClient(api_key=os.getenv("MEMANTO_API_KEY", "test_key"))
memanto_store = MemantoStore(sdk_client=sdk_client)
checkpointer = MemorySaver()

app = workflow.compile(checkpointer=checkpointer, store=memanto_store)

def run_session(user_id: str, text: str):
    config = {"configurable": {"thread_id": "1", "user_id": user_id}}
    print(f"\n--- Session for {user_id}: {text} ---")
    result = app.invoke({"user_input": text}, config=config)
    print(f"Result: {result['response']}")

if __name__ == "__main__":
    # Session A: Ingest memory
    run_session("user_alpha", "I prefer dark mode and Python 3.11")
    
    # Session B: Recall memory (Simulating a different process/thread but same user_id)
    run_session("user_alpha", "What are my preferences?")
