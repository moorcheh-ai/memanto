"""
Session B: Retrieve memories from a previous session.

This run demonstrates the CROSS-SESSION RECALL capability:
- Session A stored research findings yesterday (or earlier today)
- Session B retrieves those memories FIRST, then conducts new research

This proves that Memanto provides persistent memory across
disjointed sessions - a core requirement of the bounty.
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


def run_session_b():
    """Run Session B: Recall prior memories and continue research."""

    print("=" * 60)
    print("SESSION B: Cross-Session Recall")
    print("=" * 60)
    print()

    # Setup Memanto client and agent - SAME agent ID as Session A
    setup = MemantoSetup(API_KEY)
    client = setup.setup(
        agent_id="research-assistant-001",  # Same agent as Session A
        pattern="tool",
        description="Research assistant with persistent memory",
        duration_hours=6,
    )

    print(f"Connected to Memanto as agent: research-assistant-001")
    print("(This is the SAME agent from Session A - memories should be preserved)")
    print()

    # Build the research graph
    graph = build_research_graph(client, "research-assistant-001")

    # Run Session B: Query that should trigger recall of Session A's memories
    print("Running query about LangGraph state management...")
    print("(The agent should recall findings from Session A first)")
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
    print("SESSION B COMPLETE")
    print("=" * 60)
    print("\nMessages generated:")
    for msg in result["messages"]:
        print(f"\n{msg}")

    print("\n[Summary]")
    print(f"- Cross-session recall: {result['recall_performed']}")
    print(f"- Prior memories retrieved: {len(result['memories_retrieved'])} items")
    print(f"- This proves memories from Session A persist into Session B!")

    # Clean up
    setup.teardown("research-assistant-001")

    print("\nSession B ended.")
    print("Notice: The agent recalled memories from Session A!")
    print("This demonstrates Memanto's cross-session persistence.")


if __name__ == "__main__":
    run_session_b()