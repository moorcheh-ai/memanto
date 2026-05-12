"""
Session A: Store research memories in Memanto.

This run simulates a research session where the agent:
1. Conducts research on a topic
2. Stores findings in Memanto for future sessions

Run this script first. The memories will persist even after this session ends.
"""

import os
from dotenv import load_dotenv

from memanto.cli.client.sdk_client import SdkClient
from research_graph import build_research_graph

# Load environment
load_dotenv()

API_KEY = os.getenv("MOORCHEH_API_KEY")
if not API_KEY:
    raise ValueError("MOORCHEH_API_KEY not found in environment. Copy .env.example to .env and add your key.")


def run_session_a():
    """Run Session A: Research and store memories."""

    print("=" * 60)
    print("SESSION A: Research and Store Memories")
    print("=" * 60)
    print()

    # Setup Memanto client and agent
    setup = MemantoSetup(API_KEY)
    client = setup.setup(
        agent_id="research-assistant-001",
        pattern="tool",
        description="Research assistant with persistent memory",
        duration_hours=6,
    )

    print(f"Connected to Memanto as agent: research-assistant-001")
    print()

    # Build the research graph
    graph = build_research_graph(client, "research-assistant-001")

    # Run Session A: Research a topic and store findings
    print("Running research on 'LangGraph state management patterns'...")
    print()

    result = graph.invoke({
        "query": "What are the best practices for LangGraph state management?",
        "research_topic": "LangGraph state management patterns",
        "messages": [],
        "findings": [],
        "memories_retrieved": [],
        "final_answer": "",
        "recall_performed": False,
    })

    print("\n" + "=" * 60)
    print("SESSION A COMPLETE")
    print("=" * 60)
    print("\nMessages generated:")
    for msg in result["messages"]:
        print(f"\n{msg}")

    print("\n[Summary]")
    print(f"- Research topic: LangGraph state management patterns")
    print(f"- Findings stored in Memanto")
    print(f"- These memories will persist for Session B (even if run tomorrow)")

    # Clean up
    setup.teardown("research-assistant-001")

    print("\nSession A ended. Memories are now saved in Memanto.")
    print("Run session_b.py to retrieve these memories in a new session!")


if __name__ == "__main__":
    run_session_a()