"""
Demo script with mock output for video recording
This shows what the real output will look like
"""

import time
import sys

def typewriter(text, delay=0.03):
    """Simulate typing effect"""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def main():
    print("=" * 60)
    print("SESSION 1: Learning User Preferences")
    print("=" * 60)
    print()
    time.sleep(1)
    
    typewriter("👤 User: I prefer dark mode for all my interfaces")
    time.sleep(0.5)
    typewriter("[Stored in Memanto] User prefers dark mode for interfaces")
    time.sleep(0.5)
    typewriter("🤖 Agent: Got it! I've noted that you prefer dark mode for all interfaces. I'll remember this for future sessions.")
    print()
    time.sleep(1)
    
    typewriter("👤 User: Also, I want email notifications turned off")
    time.sleep(0.5)
    typewriter("[Stored in Memanto] User wants email notifications disabled")
    time.sleep(0.5)
    typewriter("🤖 Agent: Understood. I've saved your preference to disable email notifications.")
    print()
    time.sleep(1)
    
    typewriter("👤 User: I'm working on a Python project using FastAPI")
    time.sleep(0.5)
    typewriter("[Stored in Memanto] User is working on Python FastAPI project")
    time.sleep(0.5)
    typewriter("🤖 Agent: Great! I've noted that you're working with Python and FastAPI. Let me know if you need any help with your project.")
    print()
    time.sleep(1)
    
    print("=" * 60)
    print("✅ Session 1 complete. Preferences stored in Memanto.")
    print("=" * 60)
    print()
    time.sleep(2)
    
    print("\n" * 3)
    print("=" * 60)
    print("SESSION 2: Cross-Session Memory Recall")
    print("(Simulating a conversation the next day)")
    print("=" * 60)
    print()
    time.sleep(1)
    
    typewriter("👤 User: What theme do I prefer?")
    time.sleep(0.5)
    typewriter("[Querying Memanto...] Found: User prefers dark mode for interfaces")
    time.sleep(0.5)
    typewriter("🤖 Agent: Based on our previous conversation, you prefer dark mode for all your interfaces.")
    print()
    time.sleep(1)
    
    typewriter("👤 User: How did I configure my notifications?")
    time.sleep(0.5)
    typewriter("[Querying Memanto...] Found: User wants email notifications disabled")
    time.sleep(0.5)
    typewriter("🤖 Agent: You configured your notifications to be turned off for email.")
    print()
    time.sleep(1)
    
    typewriter("👤 User: What tech stack am I using?")
    time.sleep(0.5)
    typewriter("[Querying Memanto...] Found: User is working on Python FastAPI project")
    time.sleep(0.5)
    typewriter("🤖 Agent: You're working on a Python project using FastAPI.")
    print()
    time.sleep(1)
    
    print("=" * 60)
    print("✅ Cross-session recall successful!")
    print("=" * 60)
    print()
    typewriter("The agent remembered preferences from yesterday's session")
    typewriter("even though this is a completely new LangGraph state.")
    print()
    typewriter("This proves Memanto provides persistent memory across sessions.")

if __name__ == "__main__":
    main()
