import os
from integrations.langgraph.memanto_manager import MemantoGraphManager
from examples.langgraph_memanto.agent import create_graph

def run_persistence_test():
    AGENT_ID = "type_safe_demo_agent"
    THREAD_ID = "session_123"
    
    # --- Process 1: Initial Write ---
    print("\n--- Process 1: Initializing state ---")
    manager_1 = MemantoGraphManager(agent_id=AGENT_ID, session_id=THREAD_ID)
    graph_1 = create_graph(manager_1)
    
    config = {"configurable": {"thread_id": THREAD_ID}}
    initial_input = {"messages": [("user", "Hello, I am Alice")], "user_id": "alice_01", "context_summary": ""}
    
    output_1 = graph_1.invoke(initial_input, config)
    print(f"Process 1 Output: {output_1['messages'][-1].content}")
    
    # Simulate process termination by deleting the manager object
    del manager_1
    del graph_1

    # --- Process 2: Recall and Resume ---
    print("\n--- Process 2: Resuming from persisted state ---")
    manager_2 = MemantoGraphManager(agent_id=AGENT_ID, session_id=THREAD_ID)
    graph_2 = create_graph(manager_2)
    
    # Retrieve state using the same thread_id
    state_snapshot = graph_2.get_state(config)
    
    if state_snapshot.values:
        print(f"Recovered State: {state_snapshot.values['messages'][-1].content}")
    else:
        raise RuntimeError("State persistence failed: No values recovered in Process 2")

    # Continue interaction
    follow_up = {"messages": [("user", "Do you remember my name?")]}
    output_2 = graph_2.invoke(follow_up, config)
    print(f"Process 2 Final Output: {output_2['messages'][-1].content}")

if __name__ == "__main__":
    run_persistence_test()
