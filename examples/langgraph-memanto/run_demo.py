from __future__ import annotations

import os
from datetime import datetime

from graph import run_support_turn


def main() -> None:
    agent_id = os.getenv(
        "LANGGRAPH_DEMO_AGENT_ID",
        f"langgraph-support-demo-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    )
    customer_id = "maya-007"

    day_one = run_support_turn(
        agent_id=agent_id,
        customer_id=customer_id,
        session_label="day-1",
        message=(
            "Hi, I'm Maya. Call me MJ. I prefer dark mode and weekly email digests."
        ),
    )

    day_two = run_support_turn(
        agent_id=agent_id,
        customer_id=customer_id,
        session_label="day-2",
        message="What do you remember about how I like updates and settings?",
    )

    print(f"\nAgent ID: {agent_id}")
    print("\n=== DAY 1: memory capture ===")
    print(day_one["reply"])
    print(f"Persisted: {day_one.get('persisted_count', 0)}")

    print("\n=== DAY 2: cross-session recall ===")
    print(day_two["reply"])
    print("\nRecalled memory snippet:")
    print(day_two.get("memory_context", ""))


if __name__ == "__main__":
    main()
