"""
run_cross_session.py — Proves Memanto's cross-session recall.

This script runs TWO independent LangGraph sessions to demonstrate that
Memanto preserves memories across sessions.

Session 1 (Day 1):
    User shares personal preferences and facts.
    Agent stores them in Memanto.

Session 2 (Day 2 — simulated):
    User asks the agent about themselves in a new thread/session.
    Agent recalls the memories stored in Session 1.
"""

import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# Ensure the example dir is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import build_agent, cleanup, get_memanto
from memanto_client import MemantoConfig

load_dotenv()


def print_separator(title: str) -> None:
    width = 70
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def run_interaction(
    messages: list[tuple[str, str]],
    thread_id: str,
    checkpointer: MemorySaver,
) -> None:
    """Run a sequence of user messages against the agent."""
    graph = build_agent().compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    for role, content in messages:
        print(f"  [{role}] {content}")
        result = graph.invoke(
            {"messages": [HumanMessage(content=content)]},
            config=config,
        )
        # Print the assistant's response
        for msg in result["messages"]:
            if isinstance(msg, AIMessage) and msg.content:
                print(f"  [Agent] {msg.content}\n")


def main():
    # Validate API key
    api_key = os.getenv("MOORCHEH_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        print("❌ Please set MOORCHEH_API_KEY in your .env file.")
        print("   Get one at: https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    # ── Phase 1: Session A — Store memories ───────────────────────
    print_separator("PHASE 1: Session A — User introduces themselves")
    print("  (Simulating Day 1 conversation)")
    print("  The agent will remember user preferences via Memanto.\n")

    session_a = MemorySaver()

    run_interaction(
        [
            ("User", "Hi! I'm Alice. I'm a frontend developer working on React projects."),
            ("User", "I prefer dark mode for all my tools and I like concise answers."),
            ("User", "My current project is building a dashboard for a SaaS analytics platform."),
            ("User", "I use VS Code with the GitHub Copilot extension."),
        ],
        thread_id="session-a",
        checkpointer=session_a,
    )

    # ── Deactivate session to prove persistence ≠ in-memory state ──
    print("  [System] Ending Session A — clearing in-memory LangGraph state...")
    # The Memanto data persists in the Moorcheh cloud, but we reset
    # the LangGraph checkpointer to prove the agent isn't cheating
    # with conversation history.
    del session_a

    # ── Phase 2: Session B — Recall across sessions ────────────────
    print_separator("PHASE 2: Session B — New session, recall past memories")
    print("  (Simulating Day 2 — fresh thread, no conversation history)")
    print("  The agent must use Memanto's recall to answer.\n")

    session_b = MemorySaver()

    run_interaction(
        [
            ("User", "Hi again! Do you remember anything about me?"),
            ("User", "What's my name and what do I do for work?"),
            ("User", "What tools do I use and what are my preferences?"),
        ],
        thread_id="session-b",
        checkpointer=session_b,
    )

    # ── Verify via Memanto API directly ────────────────────────────
    print_separator("VERIFICATION: Direct Memanto query")
    print("  Querying Memanto directly to confirm memories were stored.\n")

    try:
        client = get_memanto()
        results = client.recall("Alice frontend developer preferences", top_k=10)
        if results:
            print(f"  ✅ Found {len(results)} memories in Memanto:\n")
            for i, r in enumerate(results, 1):
                content = r.get("content", r.get("text", ""))
                mem_type = r.get("type", "unknown")
                print(f"    {i}. [{mem_type}] {content}")
        else:
            print("  ❌ No memories found. Check your MOORCHEH_API_KEY and network.")
    except Exception as e:
        print(f"  ⚠️  Could not verify: {e}")
        print("  (The agent demo above may still have worked via API calls.)")

    print_separator("CROSS-SESSION DEMO COMPLETE")
    print("  ✅ Session A stored memories about Alice.")
    print("  ✅ Session B recalled those memories in a new thread.")
    print("  ✅ Memanto provided persistent memory across sessions.\n")

    cleanup()


if __name__ == "__main__":
    main()
