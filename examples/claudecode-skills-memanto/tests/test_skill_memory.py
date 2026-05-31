from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
if str(EXAMPLE_ROOT) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_ROOT))

from skill_memory import (
    DecisionTrailTap,
    LocalJsonlBackend,
    RecalledContext,
    SkillMemoryBridge,
    SkillRun,
    TranscriptDistiller,
    command_wrap,
)


class SkillMemoryTests(unittest.TestCase):
    def test_distills_explicit_markers_and_file_tags(self) -> None:
        """Explicit transcript markers become typed memories."""
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
        """The event tap records and clears mid-session decisions."""
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
        """The local backend recalls prior decisions by file overlap."""
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
        """Repeated post-skill extraction does not duplicate exact memories."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "memory.jsonl"
            backend = LocalJsonlBackend(store)
            bridge = SkillMemoryBridge(backend)
            run = SkillRun(
                skill="/handoff",
                task="Record release note",
                cwd="/repo",
                files=[],
            )
            transcript = "DECISION: Keep release notes in docs/releases.md."

            bridge.after_skill(run, transcript)
            bridge.after_skill(run, transcript)

            lines = store.read_text(encoding="utf-8").splitlines()

        self.assertEqual(1, len(lines))

    def test_distiller_ignores_malformed_event_files_field(self) -> None:
        """Malformed event file metadata does not abort distillation."""
        run = SkillRun(
            skill="/handoff",
            task="Record release note",
            cwd="/repo",
            files=[],
        )
        memories = TranscriptDistiller().distill(
            run,
            "",
            [{"kind": "decision", "content": "Keep notes short.", "files": None}],
        )

        self.assertEqual(1, len(memories))
        self.assertEqual("Keep notes short.", memories[0].content)

    def test_wrap_strips_command_separator(self) -> None:
        """The CLI wrapper accepts the conventional -- command separator."""
        old_cwd = os.getcwd()
        old_store = os.environ.get("MEMANTO_SKILLS_STORE")
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            os.environ["MEMANTO_SKILLS_STORE"] = str(Path(tmp) / "memory.jsonl")
            transcript = Path(tmp) / "transcript.txt"
            try:
                result = command_wrap(
                    [
                        "--skill",
                        "/tdd",
                        "--task",
                        "demo",
                        "--transcript",
                        str(transcript),
                        "--",
                        sys.executable,
                        "-c",
                        "print('wrapped-ok')",
                    ]
                )
            finally:
                os.chdir(old_cwd)
                if old_store is None:
                    os.environ.pop("MEMANTO_SKILLS_STORE", None)
                else:
                    os.environ["MEMANTO_SKILLS_STORE"] = old_store
            transcript_text = transcript.read_text(encoding="utf-8")

        self.assertEqual(0, result)
        self.assertIn("wrapped-ok", transcript_text)


if __name__ == "__main__":
    unittest.main()
