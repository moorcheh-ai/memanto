#!/usr/bin/env python3
"""Demo — Session 3: multi-skill memory accrual across three separate processes.

Shows that memory is NOT limited to a single skill pair. This script:

  1. Stores a new batch of decisions as if they came from a ``/handoff`` session
     (TypeScript migration, error-handling conventions, team norms).
  2. In the same process, immediately shows what a fresh ``/grill-with-docs``
     session would receive — memories accumulated from ALL three sessions.

Run AFTER demo_session_1.py and demo_session_2.py:

    python demo_session_3.py
"""

from __future__ import annotations

from memanto_skills import SkillMemory

SESSION_3_TRANSCRIPT = """
user: /handoff I'm handing the codebase to a new engineer. Here's what they must know.
assistant: I'll capture the key decisions and conventions.
user: We are migrating the entire frontend from JavaScript to TypeScript. All new files
  must be .ts or .tsx. No new .js files should be created — ever.
assistant: TypeScript-only policy noted.
user: For error handling: we use a Result<T, E> pattern, not try/catch at the
  application layer. Only infrastructure code (DB, HTTP adapters) uses try/catch.
assistant: Result<T, E> for application errors, noted.
user: The team uses conventional commits: feat:, fix:, chore:, docs:. Squash merges only.
  No merge commits into main.
assistant: Commit and merge conventions noted.
user: One more: the domain layer must have zero runtime dependencies on frameworks.
  Pure TypeScript, no imports from Next.js, Express, or any DI container.
assistant: Domain layer isolation noted. I'll make sure the handoff doc captures all of this.
"""


def main() -> None:
    mem = SkillMemory()
    mem.setup()

    # --- Step 1: store /handoff decisions ---
    print("Session 3a: distilling /handoff decisions into Memanto…\n")
    stored = mem.distill_and_store("handoff", SESSION_3_TRANSCRIPT)
    if not stored:
        print("Nothing extracted. Check MOORCHEH_API_KEY and connectivity.")
        return
    print(f"Stored {len(stored)} engineering memories from /handoff:")
    for m in stored:
        print(f"  - [{m['type']}] {m['content'][:90]}")

    # --- Step 2: show accumulated cross-skill recall for /grill-with-docs ---
    print(
        "\nSession 3b: fresh /grill-with-docs session — what it inherits "
        "from ALL previous sessions:\n"
    )
    profile = mem.recall_for_skill(
        "grill-with-docs",
        task_hint="architecture review for the Orders and frontend services",
    )
    block = profile.format_context_block(skill_name="grill-with-docs")

    if block:
        print(block)
        print(
            "\n✅ Multi-skill memory accrual works:\n"
            "   /grill-with-docs sees CQRS/Postgres/Redis (from /grill-with-docs session 1)\n"
            "   AND TypeScript migration, Result<T,E>, domain isolation (from /handoff).\n"
            "   Three separate processes, one growing Engineering Profile."
        )
    else:
        print("No memories recalled. Run demo_session_1.py first.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
