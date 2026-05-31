"""Demonstrate Memanto memory moving between separate skill runs."""

from __future__ import annotations

import argparse
from pathlib import Path

from memory_backends import FileMemoryBackend, MemantoCliBackend
from skill_memory_bridge import SkillMemoryBridge, SkillRun

REVIEW_TRANSCRIPT = """
/grill-with-docs reviewed the billing webhook plan.

Decision: Keep billing writes idempotent by Stripe event id.
Preference: Add replay tests before changing webhook behavior.
Quirk: Billing timestamps are stored as UTC ISO strings.
Constraint: Do not persist raw Stripe payloads after signature verification.
"""


def parse_args() -> argparse.Namespace:
    """Parse backend and reset options for the demo runner."""
    parser = argparse.ArgumentParser(
        description="Run the Claude Code skills + Memanto memory bridge demo.",
    )
    parser.add_argument("--backend", choices=["file", "memanto"], default="file")
    parser.add_argument("--agent-id", default="claudecode-skills-demo")
    parser.add_argument("--memory-file", default=".demo_skill_memory.json")
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run two isolated skill sessions that share memory through the bridge."""
    args = parse_args()
    if args.backend == "file" and args.reset:
        Path(args.memory_file).unlink(missing_ok=True)

    memory = (
        MemantoCliBackend(args.agent_id)
        if args.backend == "memanto"
        else FileMemoryBackend(Path(args.memory_file), source=args.agent_id)
    )
    bridge = SkillMemoryBridge(memory)

    review_run = SkillRun(
        skill_name="/grill-with-docs",
        task="Review billing webhook architecture",
        file_paths=["apps/billing/webhooks/stripe.ts", "apps/billing/db/events.ts"],
    )
    print("Session 1: /grill-with-docs finishes and stores durable memory")
    stored = bridge.after_skill(review_run, REVIEW_TRANSCRIPT)
    for item in stored:
        print(f"- remembered: {item}")

    tdd_run = SkillRun(
        skill_name="/tdd",
        task="Add tests for Stripe webhook replay and invoice creation",
        file_paths=["apps/billing/webhooks/stripe.ts", "apps/billing/webhooks/stripe.test.ts"],
    )
    print("\nSession 2: /tdd starts fresh and asks Memanto for context")
    context = bridge.before_skill(tdd_run)
    print(context)

    print("\nPrompt fragment for the next skill:")
    print(
        "Use the recalled engineering memory above when choosing test cases, "
        "fixtures, and persistence assertions."
    )


if __name__ == "__main__":
    main()
