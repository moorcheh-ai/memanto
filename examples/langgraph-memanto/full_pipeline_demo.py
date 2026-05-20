import os
from examples.langgraph_memanto.agent import create_memanto_graph
from langchain_core.messages import HumanMessage

def run_demo():
    AGENT_ID = "langgraph_persistence_demo_v1"
    
    # Session 1: Store knowledge in Thread A
    print("--- Session 1: Thread A ---")
    graph_s1 = create_memanto_graph(AGENT_ID)
    config_a = {"configurable": {"thread_id": "thread_a"}}
    
    input_s1 = {"messages": [HumanMessage(content="My name is Alice")], "user_id": "user_1"}
    graph_s1.invoke(input_s1, config_a)
    print("Stored Alice in Thread A")

    # Session 2: Store knowledge in Thread B
    print("\n--- Session 2: Thread B ---")
    graph_s2 = create_memanto_graph(AGENT_ID)
    config_b = {"configurable": {"thread_id": "thread_b"}}
    
    input_s2 = {"messages": [HumanMessage(content="My name is Bob")], "user_id": "user_2"}
    graph_s2.invoke(input_s2, config_b)
    print("Stored Bob in Thread B")

    # Session 3: Recall Thread A (Cross-process simulation)
    print("\n--- Session 3: Cross-Process Recall Thread A ---")
    graph_s3 = create_memanto_graph(AGENT_ID)
    state_a = graph_s3.get_state(config_a)
    print(f"Recovered state for Thread A: {state_a.values['messages'][-1].content}")
    
    # Session 4: Recall Thread B
    state_b = graph_s3.get_state(config_b)
    print(f"Recovered state for Thread B: {state_b.values['messages'][-1].content}")

if __name__ == "__main__":
    run_demo()
