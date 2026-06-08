import asyncio
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from integrations.langgraph.memanto_langgraph.memanto_store import MemantoStore
from integrations.langgraph.memanto_langgraph.schema import MemantoStoreConfig

class AgentState(TypedDict):
    input: str
    user_id: str
    response: str

async def memory_node(state: AgentState, config: dict, store: BaseStore):
    user_id = state["user_id"]
    namespace = ("users", user_id)
    
    # Recall existing preference
    pref = await store.get(namespace, "preference")
    
    if pref:
        state["response"] = f"I remember you like {pref.value}. Your answer is: {state['input']}"
    else:
        # Store new preference for future sessions
        await store.put(namespace, "preference", "Dark Mode")
        state["response"] = f"I've noted your preference for Dark Mode. Your answer is: {state['input']}"
    
    return state

async def main():
    config = MemantoStoreConfig(
        api_key="your_api_key",
        base_url="http://localhost:8000"
    )
    store = MemantoStore(config=config)
    
    workflow = StateGraph(AgentState)
    workflow.add_node("chat", memory_node)
    workflow.add_edge(START, "chat")
    workflow.add_edge("chat", END)
    
    app = workflow.compile(store=store)
    
    user_id = "user_123"
    
    print("--- Session 1 ---")
    input_1 = {"input": "Hello", "user_id": user_id}
    result_1 = await app.ainvoke(input_1)
    print(f"Response 1: {result_1['response']}")
    
    print("\n--- Session 2 (Cross-process simulation) ---")
    input_2 = {"input": "Hi again", "user_id": user_id}
    result_2 = await app.ainvoke(input_2)
    print(f"Response 2: {result_2['response']}")

if __name__ == "__main__":
    asyncio.run(main())
