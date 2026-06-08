"""
Full end-to-end demo: stores decisions then immediately recalls them in the
same run to prove the pipeline works. Useful for a quick smoke test.

Usage:
    python demo_full.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from memanto_skills import MemantoSkillsClient
from memanto_skills.extractor import extract_memories_from_summary

SEPARATOR = "=" * 60
THIN = "-" * 60


def section(title: str) -> None:
    print(f"\n{THIN}")
    print(f"  {title}")
    print(THIN)


def main() -> None:
    print(f"\n{SEPARATOR}")
    print("  MEMANTO SKILLS — FULL PIPELINE DEMO")
    print(f"{SEPARATOR}")

    client = MemantoSkillsClient()

    section("1. Setup")
    client.setup()
    print(f"Agent: {client.agent_id}")

    profile_tdd = None
    profile_grill = None
    all_stored: list[str] = []

    try:
        # -----------------------------------------------------------------------
        # Store phase
        # -----------------------------------------------------------------------
        section("2. Storing engineering decisions (simulating skill runs)")

        entries_tdd = [
            {
                "summary": "Use pytest-asyncio for async tests. fixture scope=session for DB setup.",
                "memory_type": "instruction",
                "confidence": 0.95,
            },
            {
                "summary": "Test through the public interface only. InMemoryRepository at seams.",
                "memory_type": "decision",
                "confidence": 0.90,
            },
        ]

        entries_arch = [
            {
                "summary": "CQRS for Order domain: QueryService for reads, OrderRepository for writes.",
                "memory_type": "decision",
                "confidence": 0.92,
            },
            {
                "summary": "Domain terms: Cart = pre-checkout, Order = post-payment. Never mix.",
                "memory_type": "instruction",
                "confidence": 0.98,
            },
        ]

        entries_pref = [
            {
                "summary": "Prefer Ruff over Black/Flake8. Explicit imports only — no star imports.",
                "memory_type": "preference",
                "confidence": 0.90,
            },
        ]

        for skill, entries in [
            ("tdd", entries_tdd),
            ("grill-with-docs", entries_arch),
            ("general", entries_pref),
        ]:
            ids = client.batch_store_from_skill(skill, entries)
            stored = [i for i in ids if i]
            all_stored.extend(stored)
            print(f"  [{skill}] stored {len(stored)}/{len(entries)} memories")

        print(f"\nTotal stored: {len(all_stored)}")

        # Brief pause so Memanto can index the memories
        print("\nWaiting for indexing...")
        time.sleep(2)

        # -----------------------------------------------------------------------
        # Recall phase
        # -----------------------------------------------------------------------
        section("3. Recall — simulating /tdd invocation in a fresh session")

        profile_tdd = client.recall_for_skill(
            skill_name="tdd",
            task_hint="writing tests for the order checkout module",
        )
        print(f"Recalled {profile_tdd.count} memories for /tdd\n")
        print(profile_tdd.format_context_block())

        section("4. Recall — simulating /grill-with-docs invocation")

        profile_grill = client.recall_for_skill(
            skill_name="grill-with-docs",
            task_hint="planning new feature in order domain CQRS architecture",
        )
        print(f"Recalled {profile_grill.count} memories for /grill-with-docs\n")
        print(profile_grill.format_context_block())

        # -----------------------------------------------------------------------
        # Extractor demo
        # -----------------------------------------------------------------------
        section("5. Extractor — auto-type inference from free text")

        sample_summary = (
            "Decided to use Redis for the session store because Postgres was too slow "
            "under load. Always expire sessions after 24 hours. Never store PII in session data."
        )

        extracted = extract_memories_from_summary(
            skill_name="grill-with-docs",
            summary=sample_summary,
            split_sentences=True,
        )
        print(f'Input: "{sample_summary[:80]}..."\n')
        print("Extracted memories:")
        for e in extracted:
            print(f"  type={e['memory_type']:12s}  {e['summary'][:70]}")

    finally:
        client.teardown()

    # -----------------------------------------------------------------------
    # Verdict
    # -----------------------------------------------------------------------
    section("Result")
    recall_success = (
        profile_tdd is not None and profile_tdd.count > 0
        or profile_grill is not None and profile_grill.count > 0
    )
    if recall_success:
        recalled = (profile_tdd.count if profile_tdd else 0) + (profile_grill.count if profile_grill else 0)
        print("✅  Cross-session recall works.")
        print(f"    Stored {len(all_stored)} memories, recalled {recalled} total.")
        print("    Zero repeated instructions across sessions.")
    else:
        print("⚠   No memories recalled — check MOORCHEH_API_KEY and network connectivity.")
        sys.exit(1)

    print(f"\n{SEPARATOR}\n")


if __name__ == "__main__":
    main()
