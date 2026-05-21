import os
from examples.langgraph_memanto.agent import create_graph

def run_cross_process_demo():
    AGENT_ID = "bounty_agent_001"
    
    # Session 1: Teach the agent something
    print("\n--- Session 1: Learning ---")
    graph_s1 = create_graph(AGENT_ID)
    config_1 = {"configurable": {"thread_id": "user_abc", "checkpoint_id": "cp1"}}
    
    inputs_1 = {
        "messages": [("user", "My favorite color is Crimson. Remember that.")],
        "user_id": "user_abc"
    }
    
    for event in graph_s1.stream(inputs_1, config=config_1):
        print(event)

    # Session 2: New process/instance, retrieve from Memanto
    print("\n--- Session 2: Recall (New Instance) ---")
    graph_s2 = create_graph(AGENT_ID)
    config_2 = {"configurable": {"thread_id": "user_abc", "checkpoint_id": "cp1"}}
    
    inputs_2 = {
        "messages": [("user", "What is my favorite color?")],
        "user_id": "user_abc"
    }
    
    for event in graph_s2.stream(inputs_2, config=config_2):
        print(event)

if __name__ == "__main__":
    run_cross_process_demo()
