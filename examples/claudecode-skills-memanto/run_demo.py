"""Credential-free demo for the Claude Code skills Memanto bridge."""

from __future__ import annotations

import argparse
from pathlib import Path

from skill_memory import LocalJsonlBackend, SkillMemoryBridge, SkillRun

STORE = Path(".demo-memanto-skills-memory.jsonl")
EVENTS = Path(".demo-memanto-skill-events.jsonl")


SESSION_A_TRANSCRIPT = "\n".join(
    [
        "/grill-with-docs: Stripe webhook architecture review",
        "",
        "DECISION: Use Stripe event_id as the durable idempotency key in "
        "app/webhooks/stripe.py.",
        "CONSTRAINT: Do not acknowledge a webhook before the database write commits.",
        "We chose a short advisory lock around event_id so parallel deliveries "
        "cannot double-create invoices.",
        "GOTCHA: The retry path must treat duplicate event_id as success, "
        "not as a 500.",
        "",
    ]
)


SESSION_B_TRANSCRIPT = """
/tdd: Write tests for the Stripe webhook path.

DECISION: Cover duplicate event_id delivery as a successful idempotent replay.
The test module should cover first delivery, duplicate delivery, and lock contention.
"""


def run_demo(reset: bool) -> None:
    """Run a two-session cross-skill memory demo."""
    if reset:
        for path in (STORE, EVENTS):
            if path.exists():
                path.unlink()

    backend = LocalJsonlBackend(STORE)
    bridge = SkillMemoryBridge(backend)

    design_run = SkillRun(
        skill="/grill-with-docs",
        task="Design Stripe webhook processing",
        cwd="/workspace/payments-service",
        files=["app/webhooks/stripe.py", "tests/test_stripe_webhooks.py"],
    )

    bridge.tap.path = EVENTS
    bridge.tap.record(
        "decision",
        "Keep webhook side effects behind a process_stripe_event(event_id) boundary.",
        files=["app/webhooks/stripe.py"],
        skill=design_run.skill,
    )
    stored = bridge.after_skill(design_run, SESSION_A_TRANSCRIPT)

    tdd_run = SkillRun(
        skill="/tdd",
        task="Write tests for Stripe webhook duplicate handling",
        cwd="/workspace/payments-service",
        files=["tests/test_stripe_webhooks.py", "app/webhooks/stripe.py"],
    )
    recalled = bridge.before_skill(tdd_run)

    print("Stored memories:")
    for memory in stored:
        print(f"- {memory.memory_type}: {memory.content}")

    print()
    print(recalled.as_env_block())

    session_b_memories = bridge.after_skill(tdd_run, SESSION_B_TRANSCRIPT)
    print()
    print("Memories from second session:")
    for memory in session_b_memories:
        print(f"- {memory.memory_type}: {memory.content}")


def main() -> None:
    """Parse demo flags and run the example."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    run_demo(reset=args.reset)


if __name__ == "__main__":
    main()
