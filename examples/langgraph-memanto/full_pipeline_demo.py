import os
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.schema import LangGraphMemantoState, MemoryType, MemantoMemoryEntry
from integrations.langgraph.coordinator import MemantoCoordinator
from integrations.langgraph.tools import create_memanto_tools

# Global Config
AGENT_ID = "arch-system-001"
sdk = SdkClient()
coordinator = MemantoCoordinator(sdk)

class AgentState(TypedDict):
    memanto: LangGraphMemantoState
    messages: Annotated[list, lambda x, y: x + y]

def memory_recall_node(state: AgentState):
    query = state["messages"][-1] if state["messages"] else ""
    updated_memanto = coordinator.synchronize_memory(state["memanto"], query)
    return {"memanto": updated_memanto}

def agent_node(state: AgentState):
    # Logic to simulate LLM deciding to store memory
    last_msg = state["messages"][-1]
    if "remember" in last_msg.lower():
        entry = MemantoMemoryEntry(
            content=last_msg, 
            memory_type=MemoryType.FACT, 
            agent_id=AGENT_ID
        )
        state["memanto"].pending_persistence.append(entry)
    return {"messages": ["Processed request"]}

def memory_persist_node(state: AgentState):
    updated_memanto = coordinator.commit_persistence(state["memanto"])
    return {"memanto": updated_memanto}

workflow = StateGraph(AgentState)
workflow.add_node("recall", memory_recall_node)
workflow.add_node("agent", agent_node)
workflow.add_node("persist", memory_persist_node)

workflow.set_entry_point("recall")
workflow.add_edge("recall", "agent")
workflow.add_edge("agent", "persist")
workflow.add_edge("persist", END)

app = workflow.compile(checkpointer=MemorySaver())

def run_session(user_input: str, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "memanto": LangGraphMemantoState(agent_id=AGENT_ID),
        "messages": [user_input]
    }
    return app.invoke(initial_state, config)

if __name__ == "__main__":
    # Session 1: Ingestion
    print("--- Session 1: Ingesting Memory ---")
    run_session("Please remember that the user prefers Python over Java", "session_1")
    
    # Session 2: Recall (Cross-process simulation)
    print("\n--- Session 2: Recalling Memory ---")
    result = run_session("What is the user's language preference?", "session_2")
    print(f"Recalled Memories: {result['memanto'].long_term_recall}")
