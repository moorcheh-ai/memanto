"""Interactive demo of Claude Code + Memanto cross-skill memory layer.

Run: python demo.py
"""

from __future__ import annotations

import os

from claudecode_memanto import MemantoConfig, SkillMemory


def main():
    """Demo the cross-skill memory layer."""
    print("🧠 Claude Code + Memanto: Cross-Skill Memory Demo")
    print("=" * 50)

    # Check for API key
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("\n⚠️  Set MOORCHEH_API_KEY to run this demo:")
        print("   export MOORCHEH_API_KEY=mch_xxxxxxxxxxxxxx")
        print("\n   Get a free key at: https://console.moorcheh.ai/api-keys")
        return

    # Initialize
    config = MemantoConfig(agent_id="claudecode-demo")
    memory = SkillMemory(config)

    print("\n📝 Simulating /tdd skill session...")
    print("-" * 40)

    # Simulate capturing from /tdd skill
    memory.capture(
        skill="tdd",
        summary=(
            "Implemented user authentication using JWT tokens. "
            "Decided to use bcrypt for password hashing instead of argon2 "
            "due to better Node.js support. Prefer integration tests over "
            "unit tests for auth flows. The API uses Express.js with "
            "TypeORM for database access."
        ),
        decisions=[
            "Use JWT for authentication (not sessions)",
            "Use bcrypt for password hashing (not argon2)",
        ],
        preferences=[
            "Prefer integration tests for auth flows",
            "Use TypeScript strict mode",
        ],
        tags=["auth", "security"],
    )

    print("\n📝 Simulating /diagnose skill session...")
    print("-" * 40)

    # Simulate capturing from /diagnose skill
    memory.capture(
        skill="diagnose",
        summary=(
            "Found memory leak in WebSocket handler. "
            "The issue was missing cleanup in useEffect. "
            "The codebase uses React 18 with concurrent features. "
            "All state management is done with Zustand (not Redux)."
        ),
        facts=[
            "React 18 with concurrent features enabled",
            "State management via Zustand (not Redux)",
            "WebSocket handlers need cleanup in useEffect",
        ],
    )

    print("\n🔍 Injecting context for /to-prd skill...")
    print("-" * 40)

    # Simulate injecting context for a new skill
    context = memory.inject(skill="to-prd")
    if context:
        print(context)
    else:
        print("(No relevant memories found)")

    print("\n✅ Demo complete!")
    print("\nIn a real workflow, the /to-prd skill would now have context")
    print("about your auth decisions, testing preferences, and tech stack.")


if __name__ == "__main__":
    main()
