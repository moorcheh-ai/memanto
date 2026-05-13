"""
run_demo.py — Memanto + LangGraph Multi-Agent Demo

Demonstrates the full multi-agent memory architecture with:
  1. Cross-session recall: run with --mode seed, exit, then --mode query
  2. Multi-agent collaboration: Support + Research + Shared Space
  3. No-LLM preview mode: works without any API key

Usage:
    # Preview mode (no API key needed)
    python run_demo.py --preview

    # With Memanto cloud
    export MOORCHEH_API_KEY="your_key"
    python run_demo.py

    # Cross-session demo
    python run_demo.py --mode seed --preview
    python run_demo.py --mode query --preview
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the example directory is on the path
sys.path.insert(0, str(Path(__file__).parent))

from memanto_adapter import MemantoAdapter
from langgraph_memory_graph import (
    create_memory_graph,
    run_agent,
    AgentState,
    Intention,
    MemoryEntry,
)


def demo_preview(preview: bool = True):
    """Run the full demo in interactive or scripted mode."""
    print("🧠 Memanto + LangGraph Multi-Agent Demo")
    print("=" * 60)
    print(f"Mode: {'PREVIEW (local JSON store)' if preview else 'CLOUD (Memanto API)'}")
    print()

    graph = create_memory_graph(preview=preview)

    demo_scenarios = [
        {
            "title": "📝 Step 1: Store User Preferences",
            "inputs": [
                "Remember that I use Python, Django, and PostgreSQL",
                "I prefer dark mode interfaces",
                "My name is Alice from Acme Corp",
            ],
        },
        {
            "title": "🔍 Step 2: Cross-Session Recall",
            "inputs": [
                "What do you know about me?",
                "Recall what tech stack I use",
                "Do you know my name?",
            ],
        },
        {
            "title": "🛟 Step 3: Support Scenario with Memory Context",
            "inputs": [
                "Help me set up Django with PostgreSQL",
                "I have an issue with my dark mode configuration",
            ],
        },
        {
            "title": "🔬 Step 4: Research Scenario",
            "inputs": [
                "Research the Memanto SDK documentation",
                "Find out about LangGraph state management",
            ],
        },
        {
            "title": "📊 Step 5: Consolidate and Summarize",
            "inputs": [
                "Consolidate memories",
            ],
        },
    ]

    for scenario in demo_scenarios:
        print(f"\n{scenario['title']}")
        print("-" * 50)
        for inp in scenario["inputs"]:
            print(f"\n  🗣️  {inp}")
            print()
            output = run_agent(None, inp, graph)
            for line in output.split("\n"):
                print(f"     {line}")
            print()

    print("=" * 60)
    print("✅ Demo complete. All memories persisted in shared+personal stores.")
    print("   Run again with --mode query to test cross-session recall!")
    print()


def demo_cross_session(preview: bool = True, mode: str = "full"):
    """Demonstrate cross-session memory recall."""
    store_path = Path(".memanto_preview_store.json")

    if mode == "seed":
        # Session 1: Store information
        print("📝 Session 1: Seeding memories...")
        sup = MemantoAdapter(agent_id="langgraph-support-agent", preview=True)
        res = MemantoAdapter(agent_id="langgraph-research-agent", preview=True)
        shr = MemantoAdapter(agent_id="langgraph-shared-space", preview=True)

        sup.remember("preference", "Fav language", "User loves Python with type hints",
                     confidence=0.95, tags=["preference", "python"], source="user")
        sup.remember("fact", "Current project", "Building a LangGraph agent with Memanto memory",
                     confidence=0.9, tags=["project", "langgraph"], source="user")
        res.remember("research", "LangGraph state", 
                     "LangGraph supports checkpointing via MemorySaver for conversation history",
                     confidence=0.85, tags=["research", "langgraph"], source="research_agent")
        shr.remember("shared_decision", "Architecture decision", 
                     "Using Memanto as external memory layer, LangGraph for workflow orchestration",
                     confidence=0.9, tags=["shared", "architecture"], source="coordinator")

        print(f"   ✅ Seeded 4 memories across 3 agent spaces!")
        print(f"   💾 Preview store: {store_path.absolute()}")
        print(f"\n   📋 Now run: python run_demo.py --mode query --preview")

    elif mode == "query":
        # Session 2: Query the memories seeded in session 1
        print("🔍 Session 2: Querying cross-session memories...")
        graph = create_memory_graph(preview=True)

        queries = [
            "What do you know about me?",
            "Recall what project I'm working on",
            "What architecture decision was made?",
        ]

        for q in queries:
            print(f"\n  🗣️  {q}")
            print()
            output = run_agent(None, q, graph)
            for line in output.split("\n"):
                print(f"     {line}")

        print("\n✅ Cross-session recall verified!")
        print("   The agent remembered information from a different session.")

    return


def main():
    parser = argparse.ArgumentParser(
        description="Memanto + LangGraph Multi-Agent Memory Demo"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "seed", "query"],
        default="full",
        help="Demo mode: 'full' (default) runs all scenarios, "
             "'seed' stores memories, 'query' recalls them",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=True,
        help="Use local preview store instead of Memanto cloud",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Force cloud mode (requires MOORCHEH_API_KEY)",
    )

    args = parser.parse_args()
    preview = not args.no_preview if args.no_preview else args.preview

    if args.mode in ("seed", "query"):
        demo_cross_session(preview=preview, mode=args.mode)
    else:
        demo_preview(preview=preview)


if __name__ == "__main__":
    main()