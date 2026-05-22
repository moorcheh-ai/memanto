#!/usr/bin/env python3
"""
Contradiction Detection Demo: Store conflicting memories and observe
how Memanto handles them with versioning and confidence adjustment.

This demonstrates Memanto's built-in contradiction detection:
- First, store a fact with high confidence
- Then, store a contradictory fact
- Recall to see how contradictions are flagged

Usage:
    python run_contradiction_demo.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langgraph_memanto import MemantoSetup, create_memanto_tools


def main():
    print("
" + "=" * 60)
    print("  Contradiction Detection Demo with Memanto")
    print("=" * 60 + "
")

    # Direct setup for fine-grained control
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY not set")
        return

    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(agent_id="contradiction-demo", pattern="tool")
    tools = create_memanto_tools(client, agent_id="contradiction-demo")

    # Step 1: Store an initial fact
    print("Step 1: Store initial fact...")
    result1 = tools["remember"].invoke({
        "memory_type": "fact",
        "title": "API rate limit",
        "content": "The API rate limit is 100 requests per minute for all users",
        "confidence": 0.9,
        "tags": "api,rate-limit",
    })
    print(f"  Stored: {result1}
")

    # Step 2: Store a contradictory fact
    print("Step 2: Store contradictory fact...")
    result2 = tools["remember"].invoke({
        "memory_type": "fact",
        "title": "API rate limit (updated)",
        "content": "The API rate limit is 1000 requests per minute for premium users",
        "confidence": 0.95,
        "tags": "api,rate-limit,premium",
    })
    print(f"  Stored: {result2}
")

    # Step 3: Recall to see how contradictions are handled
    print("Step 3: Recall memories about API rate limits...")
    result3 = tools["recall"].invoke({
        "query": "API rate limit per minute",
        "limit": 5,
    })
    print(f"  {result3}
")

    # Step 4: Use answer to see RAG synthesis
    print("Step 4: Ask a question that requires resolving the contradiction...")
    result4 = tools["answer"].invoke({
        "question": "What is the current API rate limit?",
    })
    print(f"  {result4}
")

    print("=" * 60)
    print("  Demo complete! Memanto handles contradictions with")
    print("  versioning and confidence scoring, not silent overwrites.")
    print("=" * 60 + "
")

    # Cleanup
    setup.teardown("contradiction-demo")


if __name__ == "__main__":
    main()
