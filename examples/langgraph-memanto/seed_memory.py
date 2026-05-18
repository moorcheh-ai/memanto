#!/usr/bin/env python3
"""Store Day 1 support memories for the LangGraph demo."""

from __future__ import annotations

from dotenv import load_dotenv
from memory_client import build_client, ensure_active_agent, get_agent_id

MEMORIES = [
    {
        "type": "preference",
        "title": "Response style",
        "content": "User prefers concise answers with bullet points.",
        "tags": ["support", "response-style"],
        "confidence": 0.95,
    },
    {
        "type": "fact",
        "title": "Account context",
        "content": "User is on the Pro plan and works from Europe/London.",
        "tags": ["support", "account"],
        "confidence": 0.9,
    },
    {
        "type": "commitment",
        "title": "Billing follow-up",
        "content": "Follow up after the billing migration completes.",
        "tags": ["support", "billing"],
        "confidence": 0.85,
    },
]


def main() -> None:
    load_dotenv()

    agent_id = get_agent_id()
    client = build_client()
    ensure_active_agent(
        client,
        agent_id,
        description="LangGraph customer support demo with persistent Memanto memory",
    )

    print(f"Storing Day 1 support memories for agent '{agent_id}'...")
    for memory in MEMORIES:
        result = client.remember(
            agent_id=agent_id,
            memory_type=memory["type"],
            title=memory["title"],
            content=memory["content"],
            confidence=memory["confidence"],
            tags=memory["tags"],
            source="langgraph-memanto-example",
        )
        print(f"- stored {memory['type']}: {memory['title']} ({result['memory_id']})")

    print("\nDone. Run `python run_support_agent.py` in a fresh process next.")


if __name__ == "__main__":
    main()
