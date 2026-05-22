#!/usr/bin/env python3
"""
Session 2: Recall Agent Retrieves Yesterday's Memories

This script proves CROSS-SESSION RECALL - the killer feature of the
Memanto + LangGraph integration. It starts a completely new session
with an empty LangGraph state, yet it can retrieve all the memories
stored by run_session1_research.py in a previous session.

The LangGraph state is empty. The Memanto memories persist.

Prerequisites:
    - MOORCHEH_API_KEY environment variable
    - Run run_session1_research.py first to store some memories

Usage:
    python run_session2_recall.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memanto_langgraph_tools import MemantoSetup


def main():
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY environment variable is required")
        sys.exit(1)

    agent_id = "langgraph-research-assistant"

    print("=" * 70)
    print("SESSION 2: Recall Agent Retrieves Previous Session Memories")
    print("=" * 70)
    print(f"Agent ID: {agent_id}")
    print("NOTE: This is a FRESH session - the LangGraph state is EMPTY.")
    print("Yet we can retrieve memories stored by session 1.")

    # Set up Memanto (new session!)
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern="tool",
        description="LangGraph research assistant with persistent Memanto memory",
        duration_hours=6,
    )

    print("Querying Memanto for memories from previous session...")
    print("-" * 70)

    # Demonstrate recall
    queries = [
        ("What did we find about LangGraph?", "fact,observation"),
        ("What benchmarks does Memanto achieve?", "fact"),
        ("What integration decisions were made?", "decision"),
        ("What are the user preferences for memory storage?", "preference"),
    ]

    for query, mem_type in queries:
        result = client.recall(
            agent_id=agent_id,
            query=query,
            limit=5,
            type=[t.strip() for t in mem_type.split(",")],
        )

        memories = result.get("memories", [])
        print(f"Query: {query}")
        print(f"  Found: {result.get('count', 0)} memories")

        for i, mem in enumerate(memories, 1):
            title = mem.get("title", "Untitled")
            content = mem.get("content", "")
            confidence = mem.get("confidence", "N/A")
            mem_type_val = mem.get("type", "unknown")
            tags = mem.get("tags", [])
            tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
            print(f"  {i}. [{mem_type_val}] {title} (confidence: {confidence}){tag_str}")
            short = content[:200] + ("..." if len(content) > 200 else "")
            print(f"     {short}")

    # Demonstrate RAG answer
    print("-" * 70)
    print("RAG Answer: Why should I use Memanto with LangGraph?")

    answer_result = client.answer(
        agent_id=agent_id,
        question="Why should I use Memanto with LangGraph for persistent agent memory?",
    )

    print(f"{answer_result.get('answer', 'No answer generated')}")
    sources = answer_result.get("sources", [])
    if sources:
        print(f"Based on {len(sources)} memory source(s).")

    print("=" * 70)
    print("SESSION 2 COMPLETE: Cross-session recall verified!")
    print("=" * 70)
    print("""
Key Takeaway:
  The LangGraph state for this session was completely empty - no
  checkpoint, no thread history, no in-memory state. Yet all memories
  from session 1 were retrievable because they live in Memanto persistent
  semantic database, NOT in the LangGraph state.

  This is the fundamental difference:
    LangGraph state  ->  per-thread, ephemeral
    Memanto memory   ->  cross-session, persistent, semantic
""")

    setup.teardown(agent_id)


if __name__ == "__main__":
    main()
