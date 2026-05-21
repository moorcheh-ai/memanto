import os
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointSaver
from integrations.langgraph.memanto_manager import MemantoSemanticManager

class AgentState(TypedDict):
    messages: list
    user_info: str

def memory_gate_node(state: AgentState):
    # Initialize Manager (In production, this is a singleton)
    manager = MemantoSemanticManager(
        agent_id="permanent_brain_agent", 
        api_key=os.getenv("MEMANTO_API_KEY")
    )
    
    last_message = state["messages"][-1]
    manager.process_and_store(last_message)
    return {"messages": state["messages"]}

def chat_node(state: AgentState):
    manager = MemantoSemanticManager(
        agent_id="permanent_brain_agent", 
        api_key=os.getenv("MEMANTO_API_KEY")
    )
    
    # Recall semantic memory across threads
    context = manager.recall_semantic("user preferences")
    print(f"\n[Brain Recall]: {context}")
    
    return {"messages": state["messages"] + ["Processed with long-term memory."]}

# Build Graph
builder = StateGraph(AgentState)
builder.add_node("gate", memory_gate_node)
builder.add_node("chat", chat_node)
builder.add_edge(START, "gate")
builder.add_edge("gate", "chat")
builder.add_edge("chat", END)

# The Elite Bar: compile with the custom checkpointer
checkpointer = MemantoCheckpointSaver(
    api_key=os.getenv("MEMANTO_API_KEY"), 
    agent_id="permanent_brain_agent"
)
graph = builder.compile(checkpointer=checkpointer)

def run_demo():
    # Thread A: Store secret preference
    config_a = {"configurable": {"thread_id": "thread_alpha"}}
    print("--- Executing Thread A ---")
    graph.invoke(
        {"messages": ["I prefer my reports in bullet points and love the color Obsidian."], "user_info": ""}, 
        config_a
    )

    # Thread B: Recall secret preference in a completely different thread
    config_b = {"configurable": {"thread_id": "thread_beta"}}
    print("\n--- Executing Thread B ---")
    graph.invoke(
        {"messages": ["What do I like in my reports?"], "user_info": ""}, 
        config_b
    )

if __name__ == "__main__":
    run_demo()
