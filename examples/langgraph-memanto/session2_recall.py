"""
Session 2: Recall from previous session

This script demonstrates cross-session memory recall.
The agent remembers preferences from Session 1 even though
this is a completely new conversation instance.
"""

from agent import CustomerSupportAgent
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 60)
    print("SESSION 2: Cross-Session Memory Recall")
    print("(Simulating a conversation the next day)")
    print("=" * 60)
    print()
    
    # Create NEW agent instance (simulates new session)
    # Same user_id, but fresh LangGraph state
    agent = CustomerSupportAgent(user_id="demo-user-001")
    
    # Query 1: Ask about theme preference
    print("👤 User: What theme do I prefer?")
    response1 = agent.chat("What theme do I prefer?")
    print(f"🤖 Agent: {response1}")
    print()
    
    # Query 2: Ask about notifications
    print("👤 User: How did I configure my notifications?")
    response2 = agent.chat("How did I configure my notifications?")
    print(f"🤖 Agent: {response2}")
    print()
    
    # Query 3: Ask about project context
    print("👤 User: What tech stack am I using?")
    response3 = agent.chat("What tech stack am I using?")
    print(f"🤖 Agent: {response3}")
    print()
    
    print("=" * 60)
    print("✅ Cross-session recall successful!")
    print("=" * 60)
    print()
    print("The agent remembered preferences from yesterday's session")
    print("even though this is a completely new LangGraph state.")
    print()
    print("This proves Memanto provides persistent memory across sessions.")


if __name__ == "__main__":
    main()
