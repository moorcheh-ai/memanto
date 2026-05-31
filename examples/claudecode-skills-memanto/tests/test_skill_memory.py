from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_memory import (
    DecisionTrailTap,
    LocalJsonlBackend,
    RecalledContext,
    SkillMemoryBridge,
    SkillRun,
    TranscriptDistiller,
)


class SkillMemoryTests(unittest.TestCase):
    def test_distills_explicit_markers_and_file_tags(self) -> None:
        run = SkillRun(
            skill="/grill-with-docs",
            task="Design Stripe webhook flow",
            cwd="/repo/payments",
            files=["app/webhooks/stripe.py"],
        )
        transcript = (
            "DECISION: Use event_id as the idempotency key in app/webhooks/stripe.py.\n"
            "CONSTRAINT: Do not acknowledge before the durable write commits.\n"
            "GOTCHA: Duplicate delivery should return success.\n"
        )

        memories = TranscriptDistiller().distill(run, transcript, [])

        self.assertEqual(
            ["decision", "instruction", "error"],
            [memory.memory_type for memory in memories],
        )
        self.assertIn("app/webhooks/stripe.py", memories[0].content)
        self.assertIn("file:app/webhooks/stripe.py", memories[0].tags)

    def test_event_tap_captures_mid_session_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "events.jsonl"
            tap = DecisionTrailTap(event_path)
            tap.record(
                "decision",
                "Use advisory locks around payment event ids.",
                files=["app/payments.py"],
                skill="/grill-with-docs",
            )

            events = tap.consume()

        self.assertEqual(1, len(events))
        self.assertEqual("decision", events[0]["kind"])
        self.assertFalse(event_path.exists())

    def test_local_backend_recalls_by_file_and_task_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "memory.jsonl"
            backend = LocalJsonlBackend(store)
            bridge = SkillMemoryBridge(
                backend,
                tap=DecisionTrailTap(Path(tmp) / "events.jsonl"),
            )
            first = SkillRun(
                skill="/grill-with-docs",
                task="Design Stripe webhook processing",
                cwd="/repo/payments",
                files=["app/webhooks/stripe.py"],
            )
            bridge.after_skill(
                first,
                "DECISION: Use Stripe event_id as idempotency key in "
                "app/webhooks/stripe.py.",
            )

            second = SkillRun(
                skill="/tdd",
                task="Write duplicate webhook tests",
                cwd="/repo/payments",
                files=["tests/test_stripe_webhooks.py", "app/webhooks/stripe.py"],
            )
            context = bridge.before_skill(second)

        self.assertIsInstance(context, RecalledContext)
        self.assertEqual(1, len(context.memories))
        self.assertIn("event_id", context.as_env_block())

    def test_duplicate_memories_are_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "memory.jsonl"
            backend = LocalJsonlBackend(store)
            bridge = SkillMemoryBridge(backend)
            run = SkillRun("/handoff", "Record release note", "/repo", [])
            transcript = "DECISION: Keep release notes in docs/releases.md."

            bridge.after_skill(run, transcript)
            bridge.after_skill(run, transcript)

            lines = store.read_text(encoding="utf-8").splitlines()

        self.assertEqual(1, len(lines))


if __name__ == "__main__":
    unittest.main()
