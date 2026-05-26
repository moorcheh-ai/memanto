import uuid
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointSaver
from integrations.langgraph.memanto_manager import MemoryManager
from examples.langgraph_memanto.agent import create_graph

def run_demo():
    agent_id = "prod_agent_001"
    thread_id = str(uuid.uuid4())
    sdk = SdkClient()
    
    # Setup Infrastructure
    saver = MemantoCheckpointSaver(sdk, agent_id)
    manager = MemoryManager(sdk, agent_id)
    
    # Seed a long-term memory
    manager.store_memory("User prefers Python over JavaScript", "preference")
    
    graph = create_graph(saver)
    config = {"configurable": {"thread_id": thread_id}}
    
    # Session 1: Initial Interaction
    input_1 = {"messages": [("user", "What language should I use?")], "agent_id": agent_id}
    output_1 = graph.invoke(input_1, config)
    print(f"Session 1 Response: {output_1['messages'][-1].content}")
    
    # Session 2: Cross-process persistence check
    # Re-instantiating graph and saver to simulate new process
    new_saver = MemantoCheckpointSaver(sdk, agent_id)
    new_graph = create_graph(new_saver)
    
    input_2 = {"messages": [("user", "Remind me of my preference.")], "agent_id": agent_id}
    output_2 = new_graph.invoke(input_2, config)
    print(f"Session 2 Response: {output_2['messages'][-1].content}")

if __name__ == "__main__":
    run_demo()
