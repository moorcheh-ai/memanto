import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from memanto.cli.client.sdk_client import SdkClient

class State(TypedDict):
    count: int
    messages: Annotated[list, add_messages]

def increment_node(state: State):
    return {"count": state.get("count", 0) + 1, "messages": [("assistant", "Incremented")]}

def create_app():
    AGENT_ID = "persistence_demo_agent"
    checkpointer = MemantoCheckpointer(agent_id=AGENT_ID, sdk_client=SdkClient())
    workflow = StateGraph(State)
    workflow.add_node("inc", increment_node)
    workflow.add_edge(START, "inc")
    workflow.add_edge("inc", END)
    return workflow.compile(checkpointer=checkpointer)

def run_process(step_name: str, thread_id: str, inputs: dict = None):
    print(f"--- Running {step_name} ---")
    app = create_app()
    config = {"configurable": {"thread_id": thread_id}}
    
    if inputs:
        result = app.invoke(inputs, config=config)
    else:
        result = app.invoke({}, config=config)
        
    print(f"Current Count: {result['count']}")
    return result

if __name__ == "__main__":
    THREAD = "shared_thread_88"
    
    # Process 1: Initialize and increment
    run_process("Process 1", THREAD, inputs={"count": 0, "messages": []})
    
    # Process 2: Simulate new process accessing same thread via Memanto
    run_process("Process 2", THREAD)
    
    # Process 3: Further increment
    run_process("Process 3", THREAD)
