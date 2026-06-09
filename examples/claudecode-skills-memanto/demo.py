"""Credential-free demo for the Claude Code skills + Memanto bridge."""

from __future__ import annotations

from pathlib import Path

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge

DEMO_DIR = Path(".memanto-skills-demo")
MEMORY_FILE = DEMO_DIR / "memories.jsonl"


def main() -> int:
    DEMO_DIR.mkdir(exist_ok=True)
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

    bridge = SkillMemoryBridge(LocalJsonlBackend(MEMORY_FILE))

    print("=== Session 1: /grill-with-docs stores project decisions ===")
    stored = bridge.after_skill(
        skill_name="/grill-with-docs",
        cwd="apps/acme-saas",
        paths=[
            "src/app/(dashboard)/billing/actions.ts",
            "db/migrations",
            "src/server/auth.ts",
        ],
        summary="""
Decision: Billing mutations stay in server actions under app/(dashboard)/billing.
Convention: SQLite migrations live in db/migrations/YYYYMMDDHHMM_name.sql and are append-only.
Preference: Keep authorization checks in service functions before touching database helpers.
Gotcha: Do not introduce Prisma; this SaaS uses better-sqlite3 and hand-written SQL.
""",
    )
    for memory in stored:
        print(f"stored {memory.memory_type}: {memory.content}")

    print("\n=== Session 2: /tdd starts later with an unrelated prompt ===")
    bridge = SkillMemoryBridge(LocalJsonlBackend(MEMORY_FILE))
    context = bridge.before_skill(
        skill_name="/tdd",
        cwd="apps/acme-saas",
        paths=[
            "src/app/(dashboard)/billing/actions.ts",
            "db/migrations/202606030930_add_plan_change_audit.sql",
        ],
        prompt=(
            "Add tests for changing billing plans and verify the migration rules "
            "without asking the user to repeat architecture choices."
        ),
    )
    print(context)

    required_context = ("better-sqlite3", "db/migrations", "authorization checks")
    missing = [item for item in required_context if item not in context]
    if missing:
        raise AssertionError(f"Demo context is missing: {', '.join(missing)}")

    print("\nDemo passed: the second skill received cross-session context.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
