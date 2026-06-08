"""
Demo — Session 1: Store engineering decisions.

Simulates a developer using /tdd and /grill-with-docs and capturing
their engineering decisions into Memanto.

Run this first, then run demo_session_2.py in a FRESH terminal (no shared
state) to see cross-session recall in action.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Make sure the local package is importable when running directly
sys.path.insert(0, str(Path(__file__).parent))

from memanto_skills import MemantoSkillsClient

SEPARATOR = "=" * 60


def main() -> None:
    print(f"\n{SEPARATOR}")
    print("  MEMANTO SKILLS DEMO — SESSION 1")
    print("  Storing engineering decisions")
    print(f"{SEPARATOR}\n")

    client = MemantoSkillsClient()

    print("Setting up Memanto session...")
    client.setup()

    try:
        print(f"Agent ID : {client.agent_id}")
        print(f"Recall limit : {client.recall_limit}\n")

        # -----------------------------------------------------------------------
        # Simulate decisions made during a /tdd session
        # -----------------------------------------------------------------------
        print("── /tdd session decisions ──────────────────────────────")

        tdd_decisions = [
            {
                "summary": "Always use pytest-asyncio for all async tests in this project. Never use unittest.IsolatedAsyncioTestCase.",
                "memory_type": "instruction",
                "confidence": 0.95,
            },
            {
                "summary": "Test seams are always at the public repository interface — never mock internal DB queries directly. Use InMemoryRepository adapters at the seam.",
                "memory_type": "decision",
                "confidence": 0.90,
            },
            {
                "summary": "Test naming convention: test_<action>_<condition>_<expected_outcome>. Example: test_checkout_with_empty_cart_raises_validation_error.",
                "memory_type": "instruction",
                "confidence": 0.95,
            },
            {
                "summary": "Prefer integration-style tests over unit tests. A test that mocks three collaborators is a design smell — deepen the module instead.",
                "memory_type": "preference",
                "confidence": 0.85,
            },
        ]

        ids = client.batch_store_from_skill("tdd", tdd_decisions)
        print(f"Stored {len([i for i in ids if i])} TDD decisions.\n")

        # -----------------------------------------------------------------------
        # Simulate decisions made during a /grill-with-docs session
        # -----------------------------------------------------------------------
        print("── /grill-with-docs session decisions ───────────────────")

        grill_decisions = [
            {
                "summary": "Domain term: 'Order' means a confirmed purchase with payment captured. A 'Cart' is the pre-confirmation state. Never use these interchangeably.",
                "memory_type": "instruction",
                "confidence": 0.95,
            },
            {
                "summary": "Decided to use CQRS for the Order domain. Reads go through a dedicated QueryService; writes go through the OrderRepository. Do not mix these paths.",
                "memory_type": "decision",
                "confidence": 0.90,
            },
            {
                "summary": "Architecture ADR-0003: Postgres is the write model; Redis is the read model. Never query Postgres from the read path in production.",
                "memory_type": "decision",
                "confidence": 0.95,
            },
        ]

        ids = client.batch_store_from_skill("grill-with-docs", grill_decisions)
        print(f"Stored {len([i for i in ids if i])} architecture decisions.\n")

        # -----------------------------------------------------------------------
        # Simulate a framework preference stored during general work
        # -----------------------------------------------------------------------
        print("── General preferences ──────────────────────────────────")

        general = [
            {
                "summary": "This project uses Ruff for linting and formatting. Never suggest Black or Flake8 — they are not installed.",
                "memory_type": "instruction",
                "confidence": 1.0,
                "extra_tags": ["tooling"],
            },
            {
                "summary": "Developer prefers explicit over implicit. Avoid magic, metaclasses, and decorator stacks deeper than 2 levels.",
                "memory_type": "preference",
                "confidence": 0.85,
                "extra_tags": ["style"],
            },
        ]

        ids = client.batch_store_from_skill("general", general)
        print(f"Stored {len([i for i in ids if i])} general preferences.\n")

    finally:
        client.teardown()

    print(f"{SEPARATOR}")
    print("  Session 1 complete.")
    print("  Now open a NEW terminal and run: python demo_session_2.py")
    print(f"{SEPARATOR}\n")


if __name__ == "__main__":
    main()
