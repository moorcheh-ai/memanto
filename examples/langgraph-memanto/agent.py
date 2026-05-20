from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointSaver
from memanto.cli.client.sdk_client import SdkClient

class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str

def chat_node(state: State):
    last_message = state["messages"][-1].content
    return {"messages": [("assistant", f"Processed: {last_message}")]}

def create_memanto_graph(agent_id: str):
    workflow = StateGraph(State)
    workflow.add_node("chat", chat_node)
    workflow.add_edge(START, "chat")
    workflow.add_edge("chat", END)
    
    sdk = SdkClient()
    checkpointer = MemantoCheckpointSaver(agent_id=agent_id, sdk_client=sdk)
    
    return workflow.compile(checkpointer=checkpointer)
