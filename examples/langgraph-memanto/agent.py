from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from integrations.langgraph.memanto_checkpoint import GraphState
from integrations.langgraph.memanto_manager import MemoryManager
from memanto.cli.client.sdk_client import SdkClient

class State(TypedDict):
    messages: Annotated[list, add_messages]
    semantic_memories: list
    agent_id: str

def memory_node(state: State, config: dict):
    sdk = SdkClient()
    manager = MemoryManager(sdk, state["agent_id"])
    
    last_message = state["messages"][-1].content
    memories = manager.recall_memories(last_message)
    
    return {"semantic_memories": memories}

def agent_node(state: State):
    context = "\n".join([m.content for m in state["semantic_memories"]])
    # Simulated LLM Logic
    response = f"Processed with memory: {context[:50]}..."
    return {"messages": [("assistant", response)]}

def create_graph(checkpointer):
    workflow = StateGraph(State)
    workflow.add_node("memory", memory_node)
    workflow.add_node("agent", agent_node)
    
    workflow.add_edge(START, "memory")
    workflow.add_edge("memory", "agent")
    workflow.add_edge("agent", END)
    
    return workflow.compile(checkpointer=checkpointer)
