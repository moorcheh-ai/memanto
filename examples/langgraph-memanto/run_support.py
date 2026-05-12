"""
Customer Support Agent Demo with Memanto Persistent Memory

This run demonstrates:
1. Cross-session recall: the agent checks for prior interactions with the customer
2. Personalized support: uses customer preferences from previous sessions
3. Memory persistence: stores new interactions for future reference

Run this after session_a.py and session_b.py to see full cross-session capabilities.
"""

import os
from dotenv import load_dotenv

from memanto.cli.client.sdk_client import SdkClient
from support_graph import build_support_graph

# Load environment
load_dotenv()

API_KEY = os.getenv("MOORCHEH_API_KEY")
if not API_KEY:
    raise ValueError("MOORCHEH_API_KEY not found in environment. Copy .env.example to .env and add your key.")


def run_support_demo():
    """Run a customer support interaction with persistent memory."""

    print("=" * 60)
    print("CUSTOMER SUPPORT AGENT with Cross-Session Memory")
    print("=" * 60)
    print()

    # Setup Memanto client and agent
    setup = MemantoSetup(API_KEY)
    client = setup.setup(
        agent_id="support-agent-001",
        pattern="support",
        description="Customer support agent with persistent memory",
        duration_hours=6,
    )

    print(f"Connected to Memanto as agent: support-agent-001")
    print()

    # Build the support graph
    graph = build_support_graph(client, "support-agent-001")

    # Run a support interaction
    print("Starting support interaction...")
    print()

    result = graph.invoke({
        "customer_id": "CUST-12345",
        "customer_name": "Alice Johnson",
        "issue_type": "billing inquiry",
        "issue_description": "I was charged twice for my subscription this month. I need a refund for the duplicate charge.",
        "prior_interactions": [],
        "customer_preferences": [],
        "resolution": "",
        "messages": [],
        "knowledge_retrieved": False,
    })

    print("\n" + "=" * 60)
    print("SUPPORT INTERACTION COMPLETE")
    print("=" * 60)
    print("\nConversation flow:")
    for msg in result["messages"]:
        print(f"\n{msg}")

    print("\n[Summary]")
    print(f"- Knowledge retrieved from prior sessions: {result['knowledge_retrieved']}")
    print(f"- Prior interactions: {len(result['prior_interactions'])}")
    print(f"- Customer preferences: {len(result['customer_preferences'])}")
    print(f"- Resolution provided: {len(result['resolution']) > 0}")
    print("\nThe interaction has been stored in Memanto for future reference.")

    # Clean up
    setup.teardown("support-agent-001")

    print("\nSupport session ended.")
    print("Run this again to see cross-session recall in action!")


if __name__ == "__main__":
    run_support_demo()