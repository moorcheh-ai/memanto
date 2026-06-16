#!/usr/bin/env python3
"""Bonus: contradictory memory handling for the LangGraph + Memanto demo.

Stores two contradictory preferences for the same user across two graph
runs, then surfaces them through Memanto's conflict detection and
resolves programmatically. This shows a feature Memanto has and most
"memory store" libraries do not.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime

from dotenv import load_dotenv
from langgraph_memanto import MemantoStore

from memanto.cli.client.sdk_client import SdkClient

AGENT_ID = "langgraph-contradiction-demo"
USER_ID = "alice"

OLD_MEMORY = {
    "kind": "preference",
    "title": "Loves spicy food",
    "content": "Alice loves very spicy food - the spicier the better. "
    "Always suggest the hottest option on the menu.",
    "confidence": 0.95,
    "tags": ["dietary", "spice"],
}

NEW_MEMORY = {
    "kind": "preference",
    "title": "Now avoids spicy food",
    "content": "Alice now avoids spicy food because of a recent stomach issue. "
    "Recommend mild options only until she says otherwise.",
    "confidence": 0.98,
    "tags": ["dietary", "spice", "health"],
}


async def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY not set. Copy .env.example to .env.")
        sys.exit(1)

    store = MemantoStore(api_key=api_key)
    bar = "=" * 64
    namespace = (USER_ID, "preferences")

    print(f"\n{bar}\n  Contradictory Memory Demo (LangGraph + Memanto)\n{bar}\n")
    # (try block removed)

    # Step 1: Store the initial preference via MemantoStore.
    print("Step 1: Store original preference (Alice loves spicy)...")
    await store.aput(namespace, str(uuid.uuid4()), OLD_MEMORY)
    print(f"  -> stored under namespace={namespace!r}\n")

    # Step 2: Store the contradicting preference some time later.
    print("Step 2: Store updated preference (Alice now avoids spicy)...")
    await store.aput(namespace, str(uuid.uuid4()), NEW_MEMORY)
    print(f"  -> stored under namespace={namespace!r}\n")

    # Step 3: Search and show both side-by-side.
    print("Step 3: Search the store for 'spicy food preferences'...")
    results = await store.asearch(namespace, query="spicy food preferences", limit=10)
    print(f"  Found {len(results)} memories:")
    for i, item in enumerate(results, 1):
        print(
            f"    {i}. [{item.value.get('kind')}] "
            f"{item.value.get('title')} "
            f"(confidence={item.value.get('confidence')})"
        )
        print(f"       {item.value.get('content')}")
    print()

    # Step 4: Trigger Memanto's daily summary to compute conflicts.
    print("Step 4: Generate daily summary to detect conflicts...")
    today = datetime.now().strftime("%Y-%m-%d")
    client = SdkClient(api_key=api_key)
    agent_id = f"langgraph_{USER_ID}_preferences"
    try:
        summary_result = client.generate_daily_summary(agent_id, today)
        print(
            f"  Summary status: "
            f"{summary_result.get('summary', {}).get('status', 'done')}\n"
        )
    except Exception as e:
        print(f"  Note: daily summary returned: {e}\n")

    # Step 5: Surface detected conflicts.
    print("Step 5: List detected conflicts...")
    conflicts = client.list_conflicts(agent_id, today)
    if not conflicts:
        print(
            "  No conflicts detected. (Memanto's conflict detection runs "
            "during daily summary generation and depends on semantic "
            "similarity between memories.)\n"
        )
    else:
        print(f"  Found {len(conflicts)} conflict(s):")
        for i, c in enumerate(conflicts, 1):
            print(f"    {i}. {c.get('description', 'N/A')}")
            print(f"       severity={c.get('severity', 'N/A')}")
        print()

        # Step 6: Resolve by keeping the newer memory.
        print("Step 6: Resolve conflict (keep_new - the recent stomach issue)...")
        resolved = client.resolve_conflict(
            agent_id=agent_id,
            date=today,
            conflict_index=0,
            action="keep_new",
        )
        print(f"  Resolution status: {resolved.get('status', 'resolved')}\n")

    # Step 7: Verify by re-searching the store.
    print("Step 7: Re-search the store to verify final state...")
    final = await store.asearch(namespace, query="spicy food preferences", limit=10)
    print(f"  Now {len(final)} memories remain:")
    for item in final:
        print(f"    - {item.value.get('title')}: {item.value.get('content')}")

    print(f"\n{bar}\n  Contradiction demo complete.\n{bar}\n")


if __name__ == "__main__":
    asyncio.run(main())
