"""
Session 1: Store user preferences in Memanto

This script demonstrates the first conversation where the agent
learns and stores user preferences in long-term memory.
"""

from agent import CustomerSupportAgent
import os
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 60)
    print("SESSION 1: Learning User Preferences")
    print("=" * 60)
    print()
    
    # Create agent for user
    agent = CustomerSupportAgent(user_id="demo-user-001")
    
    # Conversation 1: User states preferences
    print("👤 User: I prefer dark mode for all my interfaces")
    response1 = agent.chat("I prefer dark mode for all my interfaces")
    print(f"🤖 Agent: {response1}")
    print()
    
    # Conversation 2: User states another preference
    print("👤 User: Also, I want email notifications turned off")
    response2 = agent.chat("Also, I want email notifications turned off")
    print(f"🤖 Agent: {response2}")
    print()
    
    # Conversation 3: User provides context
    print("👤 User: I'm working on a Python project using FastAPI")
    response3 = agent.chat("I'm working on a Python project using FastAPI")
    print(f"🤖 Agent: {response3}")
    print()
    
    print("=" * 60)
    print("✅ Session 1 complete. Preferences stored in Memanto.")
    print("=" * 60)
    print()
    print("Next: Run session2_recall.py to see cross-session memory in action!")


if __name__ == "__main__":
    main()
