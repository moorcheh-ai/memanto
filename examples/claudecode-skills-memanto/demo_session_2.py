"""
Demo — Session 2: Cross-session recall.

Starts with a completely clean Python process (no shared state with Session 1),
recalls the engineering profile, and proves the context was preserved.

Run AFTER demo_session_1.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from memanto_skills import MemantoSkillsClient

SEPARATOR = "=" * 60


def main() -> None:
    print(f"\n{SEPARATOR}")
    print("  MEMANTO SKILLS DEMO — SESSION 2")
    print("  Cross-session recall (fresh process, no shared state)")
    print(f"{SEPARATOR}\n")

    # Completely new client — no variables from Session 1
    client = MemantoSkillsClient()
    client.setup()

    print(f"Agent ID : {client.agent_id}")
    print(f"Recall limit : {client.recall_limit}\n")

    # -----------------------------------------------------------------------
    # Recall 1: Before a /tdd session
    # -----------------------------------------------------------------------
    print("── Recall before /tdd ───────────────────────────────────")
    print("(What Claude Code would see before running /tdd)\n")

    profile = client.recall_for_skill(
        skill_name="tdd",
        task_hint="writing tests for the checkout module",
    )

    print(f"Recalled {profile.count} memories.\n")
    print(profile.format_context_block())

    print()

    # -----------------------------------------------------------------------
    # Recall 2: Before a /grill-with-docs session
    # -----------------------------------------------------------------------
    print("── Recall before /grill-with-docs ───────────────────────")
    print("(What Claude Code would see before a grilling session)\n")

    profile2 = client.recall_for_skill(
        skill_name="grill-with-docs",
        task_hint="planning a new feature in the Order domain",
    )

    print(f"Recalled {profile2.count} memories.\n")
    print(profile2.format_context_block())

    print()

    # -----------------------------------------------------------------------
    # Recall 3: Filtered — instructions only
    # -----------------------------------------------------------------------
    print("── Recall: instructions only ────────────────────────────")
    print("(Hard rules this agent must always follow)\n")

    profile3 = client.recall_for_skill(
        skill_name="profile",
        task_hint="hard rules conventions instructions",
        memory_types=["instruction"],
    )

    if profile3.is_empty:
        print("No instructions stored yet.")
    else:
        print(f"Found {profile3.count} instructions:\n")
        print(profile3.format_context_block())

    client.teardown()

    print(f"\n{SEPARATOR}")
    print("  Session 2 complete.")
    print("  Cross-session recall works: no state was shared between processes.")
    print(f"{SEPARATOR}\n")


if __name__ == "__main__":
    main()
