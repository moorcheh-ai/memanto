import os
import uuid
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer
from examples.langgraph_memanto.agent import workflow, AGENT_ID
from memanto.cli.client.sdk_client import SdkClient

def run_session(session_name: str, user_input: str, thread_id: str):
    print(f"\n--- Starting Session: {session_name} ---")
    sdk = SdkClient()
    checkpointer = MemantoCheckpointer(sdk, AGENT_ID)
    
    app = workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    
    inputs = {"messages": [("user", user_input)]}
    for event in app.stream(inputs, config=config):
        for value in event.values():
            print("Assistant:", value["messages"][-1].content)

if __name__ == "__main__":
    # Shared thread ID to prove cross-process persistence via Memanto
    shared_thread_id = "user_1234_session_alpha"
    
    # Process 1: Establish a fact
    run_session(
        "Session A: Ingestion", 
        "My favorite color is Obsidian Blue. Please remember that.", 
        shared_thread_id
    )
    
    # Process 2: Recall the fact in a separate execution context
    run_session(
        "Session B: Recall", 
        "Do you remember what my favorite color is?", 
        shared_thread_id
    )
