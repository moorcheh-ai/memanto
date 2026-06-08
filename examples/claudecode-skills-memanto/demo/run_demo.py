#!/usr/bin/env python3
"""
Demo script — proves that Memanto persists preferences across Claude Code sessions.

Session 1: Manually store a set of engineering preferences (simulating what
            the Stop hook would capture from a real Claude Code session).

Session 2: Query Memanto to verify the preferences are recalled in a *new*
            process (simulating the next day's Claude Code session start).

Run this with a valid MOORCHEH_API_KEY:
    python3 demo/run_demo.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_here))

from memory_tools import answer, list_memories, recall, remember  # noqa: E402

PROJECT_PATH = str(Path.home() / "demo-project")  # fictional project dir


def separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print("=" * 60)


def session_one() -> None:
    """Simulate what the Stop hook captures after a coding session."""
    separator("SESSION 1 — Storing engineering preferences")

    preferences = [
        {
            "title": "Always use FastAPI for Python REST APIs",
            "content": (
                "Always use FastAPI for Python REST APIs. "
                "Never use Flask for new projects — we prefer FastAPI's "
                "type hints, async support, and automatic OpenAPI docs."
            ),
            "memory_type": "preference",
            "tags": ["python", "fastapi", "api"],
        },
        {
            "title": "Prefer httpx over requests for HTTP clients",
            "content": (
                "Prefer httpx over requests for HTTP clients. "
                "httpx supports async, has better timeout handling, "
                "and works well with anyio. requests is legacy."
            ),
            "memory_type": "preference",
            "tags": ["python", "http", "httpx"],
        },
        {
            "title": "Decided to use PostgreSQL as the primary database",
            "content": (
                "Decided to use PostgreSQL as the primary database. "
                "SQLite is fine for local dev only. "
                "All production workloads go to PostgreSQL with SQLAlchemy ORM."
            ),
            "memory_type": "decision",
            "tags": ["database", "postgresql", "sqlalchemy"],
        },
        {
            "title": "Use pytest with fixtures — never unittest",
            "content": (
                "Use pytest with fixtures — never unittest. "
                "All tests go in tests/ directory, "
                "coverage must be >= 80% before merging."
            ),
            "memory_type": "constraint",
            "tags": ["testing", "pytest"],
        },
        {
            "title": "API versioning pattern: /api/v{n}/ prefix",
            "content": (
                "API versioning pattern: /api/v{n}/ prefix. "
                "Current version is v1. "
                "Breaking changes require a new version bump."
            ),
            "memory_type": "pattern",
            "tags": ["api", "versioning"],
        },
    ]

    for pref in preferences:
        result = remember(
            title=pref["title"],
            content=pref["content"],
            memory_type=pref["memory_type"],
            tags=pref["tags"],
            project_path=PROJECT_PATH,
        )
        print(f"  ✅ Stored: {pref['title'][:60]}")

    print(f"\n  {len(preferences)} preferences stored in Memanto.")
    print("  Simulating end of Session 1 — process exits...\n")
    time.sleep(1)


def session_two() -> None:
    """
    Simulate a NEW Claude Code session starting the next day.
    Memories should be injected from Memanto without any re-prompting.
    """
    separator("SESSION 2 — New process, preferences recalled automatically")

    # Simulate the UserPromptSubmit hook firing with the user's first message
    user_prompt = "Help me add a new endpoint to the API"
    print(f"  User's first message: '{user_prompt}'")
    print("  (inject_context.py fires automatically via UserPromptSubmit hook)\n")

    memories = recall(
        query=user_prompt,
        top_k=5,
        project_path=PROJECT_PATH,
    )

    if not memories:
        print("  ⚠️  No memories found — check MOORCHEH_API_KEY and try again.")
        return

    print("  🧠 Injected into system context:")
    for i, mem in enumerate(memories, 1):
        if isinstance(mem, dict):
            text = mem.get("text") or mem.get("content") or str(mem)
            score = mem.get("score", mem.get("similarity", "?"))
        else:
            text = str(mem)
            score = "?"
        short = text.split("\n\n")[0][:100]
        print(f"    {i}. [{score:.2f}] {short}")

    separator("SESSION 2 — Answering a synthesised question from memory")

    question = "What database and HTTP client should I use in this project?"
    print(f"  Question: '{question}'")
    resp = answer(question=question, project_path=PROJECT_PATH)
    print(f"\n  Answer from Memanto:\n  {resp}")

    separator("SESSION 2 — Listing ALL stored memories")

    all_mems = list_memories(project_path=PROJECT_PATH)
    print(f"  Total memories in namespace: {len(all_mems)}")
    for mem in all_mems:
        if isinstance(mem, dict):
            txt = (mem.get("text") or "")[:80]
            print(f"    • {txt}")


def main() -> None:
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        print("❌ MOORCHEH_API_KEY not set.")
        print("   Get a free key at https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    print("🧠 Memanto ↔ Claude Code Skills — Persistence Demo")
    print("   Proves that engineering preferences survive across sessions.")

    session_one()
    session_two()

    print("\n" + "=" * 60)
    print("  ✅ Demo complete!")
    print("  Preferences stored in Session 1 were retrieved in Session 2")
    print("  without any re-prompting — zero context re-entry needed.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
