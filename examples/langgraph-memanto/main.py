"""
Memanto + LangGraph: Cross-Session Recall Demo

This script demonstrates how Memanto provides a "Permanent Brain" for LangGraph
agents, allowing them to remember information across disjointed execution runs.
"""

import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from memanto_tools import MemantoToolbox
from agent import create_memanto_agent

# Load environment variables (OPENAI_API_KEY, MOORCHEH_API_KEY)
load_dotenv()

def run_demo():
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        print("Please set MOORCHEH_API_KEY in your .env file")
        return

    # Use a consistent agent_id to demonstrate cross-session recall
    agent_id = "langgraph-researcher-001"
    
    # Initialize Memanto Toolbox and Tools
    toolbox = MemantoToolbox(api_key=api_key, agent_id=agent_id)
    tools = toolbox.get_tools()
    
    # Create the LangGraph agent
    agent = create_memanto_agent("gpt-4-turbo-preview", tools)

    print("\n--- SESSION 1: Learning something new ---")
    session1_input = {
        "messages": [
            HumanMessage(content=(
                "Please remember that the secret code for Project Phoenix is 'PHOENIX-2026'. "
                "Store this as a 'fact' in your memory so you don't forget it in future sessions."
            ))
        ]
    }
    
    for event in agent.stream(session1_input):
        for value in event.values():
            last_message = value["messages"][-1]
            if hasattr(last_message, "content") and last_message.content:
                print(f"Agent: {last_message.content[:100]}...")

    print("\n--- SESSION 1 COMPLETE ---")
    print("Agent has stored the information in Memanto.")
    print("Simulating a complete process restart (disjointed session)...")

    # In a real scenario, the script would end here and be run again later.
    # We'll just re-initialize everything to prove it works.
    
    print("\n--- SESSION 2: Recalling from the past ---")
    
    # New toolbox, new agent instance, same agent_id
    toolbox_v2 = MemantoToolbox(api_key=api_key, agent_id=agent_id)
    tools_v2 = toolbox_v2.get_tools()
    agent_v2 = create_memanto_agent("gpt-4-turbo-preview", tools_v2)

    session2_input = {
        "messages": [
            HumanMessage(content=(
                "Hey! Do you remember the secret code for Project Phoenix? "
                "Use your recall tool to find it."
            ))
        ]
    }

    for event in agent_v2.stream(session2_input):
        for value in event.values():
            last_message = value["messages"][-1]
            if hasattr(last_message, "content") and last_message.content:
                print(f"Agent: {last_message.content}")

    print("\n--- SESSION 2 COMPLETE ---")

if __name__ == "__main__":
    run_demo()
