#!/usr/bin/env python3
"""
Bonus: Contradictory Memory Handling

Demonstrates Memanto's conflict detection when an agent stores a new
fact that contradicts a previously stored one. Shows how to detect
and resolve memory conflicts programmatically.

Usage:
    python run_contradiction.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from memanto_crewai import MemantoSetup

AGENT_ID = "crewai-contradiction-demo"


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)

    setup = MemantoSetup(api_key)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Demo agent for contradictory memory handling",
    )

    print(f"\n{'=' * 60}")
    print("  Contradictory Memory Demo")
    print(f"{'=' * 60}\n")

    try:
        # Step 1: Store initial fact
        print("Step 1: Storing initial market size fact...")
        result1 = client.remember(
            agent_id=AGENT_ID,
            memory_type="fact",
            title="AI Agent Market Size 2025",
            content="The global AI agent framework market was valued at $5.1 billion in 2025.",
            confidence=0.9,
            tags=["market-size", "ai-agents", "2025"],
            source="crewai-demo",
            provenance="explicit_statement",
        )
        print(f"  Stored: {result1['memory_id']}")
        print("  Content: 'Market valued at $5.1 billion in 2025'\n")

        # Step 2: Store contradictory fact (updated figure)
        print("Step 2: Storing updated (contradictory) market size fact...")
        result2 = client.remember(
            agent_id=AGENT_ID,
            memory_type="fact",
            title="AI Agent Market Size 2025 (Revised)",
            content="The global AI agent framework market was valued at $8.3 billion in 2025, revised upward.",
            confidence=0.95,
            tags=["market-size", "ai-agents", "2025"],
            source="crewai-demo",
            provenance="corrected",
        )
        print(f"  Stored: {result2['memory_id']}")
        print("  Content: 'Market valued at $8.3 billion in 2025 (revised)'\n")

        # Step 3: Recall all market size memories
        print("Step 3: Recalling all market size memories...")
        recall_result = client.recall(
            agent_id=AGENT_ID,
            query="AI agent market size 2025",
            limit=10,
            type=["fact"],
        )
        memories = recall_result.get("memories", [])
        print(f"  Found {len(memories)} memories:\n")
        for i, mem in enumerate(memories, 1):
            print(f"  {i}. {mem.get('title', 'Untitled')}")
            print(f"     Content: {mem.get('content', '')}")
            print(f"     Confidence: {mem.get('confidence', 'N/A')}")
            print(f"     Provenance: {mem.get('provenance', 'N/A')}")
            print()

        # Step 4: Generate daily summary to trigger conflict detection
        print("Step 4: Generating daily summary to detect conflicts...")
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            summary_result = client.generate_daily_summary(AGENT_ID, today)
            print(
                f"  Summary generated: {summary_result.get('summary', {}).get('status', 'done')}"
            )
        except Exception as e:
            print(f"  Summary generation note: {e}")

        # Step 5: Check for conflicts
        print("\nStep 5: Checking for detected conflicts...")
        conflicts = client.list_conflicts(AGENT_ID, today)
        if conflicts:
            print(f"  Found {len(conflicts)} conflict(s):\n")
            for i, conflict in enumerate(conflicts):
                print(f"  Conflict {i + 1}:")
                print(f"    Description: {conflict.get('description', 'N/A')}")
                print(f"    Severity: {conflict.get('severity', 'N/A')}")
                print()

            # Step 6: Resolve conflict
            print(
                "Step 6: Resolving conflict (keeping the newer, higher-confidence value)..."
            )
            resolve_result = client.resolve_conflict(
                agent_id=AGENT_ID,
                date=today,
                conflict_index=0,
                action="keep_new",
            )
            print(f"  Resolution: {resolve_result.get('status', 'resolved')}")
        else:
            print("  No conflicts detected in the report.")
            print("  (Conflict detection runs during daily summary generation.)")

        # Step 7: Verify with semantic recall (recall_current API removed)
        print("\nStep 7: Recalling memories for verification...")
        current = client.recall(
            agent_id=AGENT_ID,
            query="AI agent market size",
            limit=5,
            type=["fact"],
        )
        current_memories = current.get("memories", [])
        print(f"  Current memories: {len(current_memories)}")
        for mem in current_memories:
            print(f"    - {mem.get('title', 'Untitled')}: {mem.get('content', '')}")

        print(f"\n{'=' * 60}")
        print("  Contradiction Demo Complete!")
        print(f"{'=' * 60}")

    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()
