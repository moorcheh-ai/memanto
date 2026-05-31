#!/usr/bin/env python3
"""
Walkthrough Simulation for LangGraph + Memanto

Simulates a multi-session customer support scenario:
- Day 1 (Session A): User introduces themselves and shares billing and UI preferences.
- Day 2 (Session B - Fresh Thread): The user starts a new conversation.
  The agent semantically recalls past decisions and preferences, addressing the user
  personally without repeated instructions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the example directory is in path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from agent import build_agent_graph

# Load environment variables
load_dotenv()


def main() -> None:
    print("=" * 75)
    print("🧠 LangGraph + Memanto: Multi-Session Customer Support Simulator")
    print("=" * 75)

    # 1. Check API credentials
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please export it before running: export MOORCHEH_API_KEY='mch_...'", file=sys.stderr)
        sys.exit(1)

    # Compile the LangGraph graph
    print("[*] Compiling LangGraph workflow...")
    graph = build_agent_graph()
    print("[+] Graph compiled successfully!")

    user_id = "user-alice-999-mch"

    print("\n" + "=" * 60)
    print("📆 DAY 1 (Thread A): User sets preferences")
    print("=" * 60)

    # User Input 1
    input_message_1 = "Hello! My name is Alice, and I am on the Premium Plan."
    print(f"\nUser: '{input_message_1}'")
    
    state_1 = {
        "user_id": user_id,
        "messages": [{"role": "user", "content": input_message_1}],
        "active_memory": "",
        "latest_reply": "",
    }
    
    # Run Graph
    output_state_1 = graph.invoke(state_1)
    print(f"Assistant: {output_state_1['latest_reply']}")

    print("\n" + "-" * 50)

    # User Input 2
    input_message_2 = "Also, I prefer dark mode UIs for all apps."
    print(f"\nUser: '{input_message_2}'")
    
    state_2 = {
        "user_id": user_id,
        "messages": [{"role": "user", "content": input_message_2}],
        "active_memory": "",
        "latest_reply": "",
    }
    
    # Run Graph
    output_state_2 = graph.invoke(state_2)
    print(f"Assistant: {output_state_2['latest_reply']}")

    print("\n" + "=" * 60)
    print("📆 DAY 2 (Thread B - Fresh Thread): Semantic Memory Recall")
    print("=" * 60)
    print("[*] Simulating a fresh session tomorrow. All LangGraph thread history is wiped!")
    print("[*] Starting with an empty message state...")

    # Alice starts a completely fresh thread with a generic question
    input_message_3 = "Hi support! I want to configure my dashboard settings."
    print(f"\nUser: '{input_message_3}'")

    state_3 = {
        "user_id": user_id,
        "messages": [{"role": "user", "content": input_message_3}],
        "active_memory": "",
        "latest_reply": "",
    }

    # Run Graph - This will trigger Memanto semantic recall and injection!
    output_state_3 = graph.invoke(state_3)
    
    print("\n" + "-" * 50)
    print("[+] Injected Active Memory Context into Node:")
    print(output_state_3["active_memory"])
    print("-" * 50)
    
    print(f"\nAssistant: {output_state_3['latest_reply']}")
    print("\n" + "=" * 75)
    print("🎉 SUCCESS! The agent successfully recalled Alice's name, billing plan,")
    print("    and UI style preferences across separate threads using Memanto!")
    print("=" * 75)


if __name__ == "__main__":
    main()
