#!/usr/bin/env python3
"""
Session 1: Research Agent Stores Findings in Memanto

This script simulates a research session where the agent investigates
a topic and stores key findings as persistent Memanto memories. These
memories will survive after the session ends and be retrievable in
future sessions via run_session2_recall.py.

This demonstrates the core value proposition: Memanto memories persist
outside the standard LangGraph state, enabling true cross-session recall.

Prerequisites:
    - MOORCHEH_API_KEY environment variable
    - OPENAI_API_KEY environment variable

Usage:
    python run_session1_research.py
"""

import os
import sys

# Ensure the current directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memanto_langgraph_tools import MemantoSetup


def main():
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("ERROR: MOORCHEH_API_KEY environment variable is required")
        print("Get one at https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    agent_id = "langgraph-research-assistant"

    print("=" * 70)
    print("SESSION 1: Research Agent Stores Findings")
    print("=" * 70)
    print(f"\nAgent ID: {agent_id}")
    print("This session will store research findings as persistent memories.")
    print("Close this terminal, wait any amount of time, then run session 2")
    print("to prove the memories survive across sessions.\n")

    # Set up Memanto
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern="tool",
        description="LangGraph research assistant with persistent Memanto memory",
        duration_hours=6,
    )

    # Simulate research findings that the agent would store
    research_findings = [
        {
            "memory_type": "fact",
            "title": "LangGraph market position",
            "content": "LangGraph is the leading framework for building stateful, multi-step AI agents. It extends LangChain with graph-based workflow orchestration, supporting cycles, branching, and persistent checkpointing.",
            "confidence": 0.95,
            "tags": ["langgraph", "market", "ai-agents"],
        },
        {
            "memory_type": "observation",
            "title": "Agent memory gap identified",
            "content": "Most agent frameworks lack persistent cross-session memory. LangGraph's checkpointing only persists within a single thread — it cannot recall information from a different conversation or a previous day's session without external storage.",
            "confidence": 0.9,
            "tags": ["langgraph", "memory", "limitation", "observation"],
        },
        {
            "memory_type": "fact",
            "title": "Memanto benchmarks",
            "content": "Memanto achieves 89.8% on LongMemEval and 87.1% on LoCoMo benchmarks, outperforming Mem0, Mem0g, Zep, and Letta. It uses Moorcheh's information-theoretic retrieval engine for sub-90ms semantic search.",
            "confidence": 0.95,
            "tags": ["memanto", "benchmarks", "performance", "retrieval"],
        },
        {
            "memory_type": "learning",
            "title": "Integration pattern: external memory layer",
            "content": "The most effective pattern for giving LangGraph agents persistent memory is to use an external memory service (like Memanto) as a tool within the agent's workflow. The agent calls remember/recall explicitly, making memory operations transparent and controllable.",
            "confidence": 0.85,
            "tags": ["integration", "pattern", "learning", "architecture"],
        },
        {
            "memory_type": "decision",
            "title": "Chose Memanto over Mem0 for LangGraph integration",
            "content": "We chose Memanto over Mem0 for the LangGraph integration because: (1) zero ingestion latency vs Mem0's LLM extraction bottleneck, (2) typed semantic memory with 13 categories vs Mem0's flat approach, (3) built-in confidence scoring and provenance tracking, (4) superior benchmark performance on LongMemEval and LoCoMo.",
            "confidence": 0.9,
            "tags": ["decision", "memanto", "mem0", "comparison"],
        },
        {
            "memory_type": "preference",
            "title": "User prefers concise atomic memories",
            "content": "When storing research findings as memories, the user prefers each memory to be atomic (one fact per memory) with descriptive titles and relevant tags for better future retrieval.",
            "confidence": 0.8,
            "tags": ["preference", "memory-storage", "user"],
        },
    ]

    print("Storing research findings as persistent memories...\n")

    stored_ids = []
    for i, finding in enumerate(research_findings, 1):
        result = client.remember(
            agent_id=agent_id,
            memory_type=finding["memory_type"],
            title=finding["title"],
            content=finding["content"],
            confidence=finding["confidence"],
            tags=finding["tags"],
            source="langgraph-research-agent",
            provenance="explicit_statement",
        )
        stored_ids.append(result["memory_id"])
        print(f"  ✓ [{finding['memory_type']}] {finding['title']}")
        print(f"    ID: {result['memory_id']} | Confidence: {finding['confidence']}")

    print(f"\n{'─' * 70}")
    print(f"SESSION 1 COMPLETE: Stored {len(stored_ids)} memories")
    print(f"{'─' * 70}")
    print("\n✅ These memories now exist OUTSIDE the LangGraph state.")
    print("✅ They will persist even after this process exits.")
    print("✅ Run `python run_session2_recall.py` to prove cross-session recall.")
    print()

    # Clean up session
    setup.teardown(agent_id)
    print("Session deactivated. Memories remain stored in Memanto.")


if __name__ == "__main__":
    main()
