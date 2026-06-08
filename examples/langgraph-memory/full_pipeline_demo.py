import os
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from integrations.langgraph.memanto_store import MemantoStore, MemantoStoreConfig

class AgentState(TypedDict):
    user_id: str
    input: str
    context: str
    response: str

def retrieve_memory_node(state: AgentState, config: dict, store: MemantoStore):
    # Use the BaseStore search abstraction for cross-thread memory
    namespace = ("memories", state["user_id"])
    memories = list(store.search(namespace, query=state["input"], limit=3))
    context = " ".join([str(m) for m in memories])
    return {"context": context}

def process_node(state: AgentState):
    # Simulate logic that uses the retrieved context
    response = f"Processed {state['input']} with memory: {state['context']}"
    return {"response": response}

def store_memory_node(state: AgentState, config: dict, store: MemantoStore):
    # Persist the interaction for future cross-process recall
    namespace = ("memories", state["user_id"])
    store.put(namespace, state["input"], state["response"])
    return {}

def run_pipeline():
    # Setup Store with Dependency Injection
    store_config = MemantoStoreConfig(
        api_key=os.getenv("MEMANTO_API_KEY", "test_key"),
        base_url=os.getenv("MEMANTO_URL", "http://localhost:8000")
    )
    memanto_store = MemantoStore(config=store_config)
    checkpointer = MemorySaver()

    # Build Graph
    builder = StateGraph(AgentState)
    builder.add_node("retrieve", retrieve_memory_node)
    builder.add_node("process", process_node)
    builder.add_node("store", store_memory_node)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "process")
    builder.add_edge("process", "store")
    builder.add_edge("store", END)

    graph = builder.compile(checkpointer=checkpointer, store=memanto_store)

    # Execution 1: Initial knowledge ingestion
    user_id = "user_123"
    input_1 = "My favorite color is Obsidian Blue"
    graph.invoke(
        {"user_id": user_id, "input": input_1}, 
        config={"configurable": {"thread_id": "1"}}
    )

    # Execution 2: Cross-thread recall (different thread_id, same user_id)
    # This proves the BaseStore (Memanto) is working independently of the Checkpointer
    input_2 = "What is my favorite color?"
    result = graph.invoke(
        {"user_id": user_id, "input": input_2}, 
        config={"configurable": {"thread_id": "2"}}
    )
    
    print(f"User Input: {input_2}")
    print(f"Agent Response: {result['response']}")

if __name__ == "__main__":
    run_pipeline()
