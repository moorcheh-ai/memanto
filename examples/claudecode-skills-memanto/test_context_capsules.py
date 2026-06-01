from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from context_capsules import (
    CapsuleExtractor,
    LocalCapsuleStore,
    SecretRedactor,
    format_context_block,
)


class ContextCapsuleTests(unittest.TestCase):
    def test_extracts_typed_capsules_and_redacts_secrets(self) -> None:
        transcript = "\n".join(
            [
                "Decision: Use advisory locks for invoice writes.",
                "Gotcha: Do not log API_KEY=sk_live_abc123456789.",
            ]
        )

        capsules = CapsuleExtractor().extract(
            transcript,
            project="demo",
            files=["src/billing.py"],
            source_skill="/grill-with-docs",
            session_id="s1",
        )

        self.assertEqual([capsule.kind for capsule in capsules], ["decision", "gotcha"])
        self.assertEqual(capsules[1].content, "Do not log API_KEY=<redacted>.")
        self.assertEqual(capsules[1].redactions, 1)

    def test_local_store_recalls_by_project_file_and_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalCapsuleStore(Path(temp_dir) / "capsules.jsonl")
            capsules = CapsuleExtractor().extract(
                "Decision: Stripe webhook handlers must be idempotent by event id.",
                project="shop",
                files=["src/billing/webhooks.py"],
                source_skill="/handoff",
                session_id="s1",
            )
            store.append_many(capsules)

            matches = store.recall(
                project="shop",
                task="/tdd duplicate Stripe webhook tests",
                files=["src/billing/webhooks.py"],
                limit=3,
            )

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0][1].content.startswith("Stripe webhook handlers"))
        self.assertIn("MEMANTO_CONTEXT", format_context_block(matches))

    def test_unrelated_memories_are_not_recalled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalCapsuleStore(Path(temp_dir) / "capsules.jsonl")
            capsules = CapsuleExtractor().extract(
                "Preference: Keep CSS modules colocated with marketing pages.",
                project="site",
                files=["app/marketing/page.tsx"],
                source_skill="/handoff",
                session_id="s1",
            )
            store.append_many(capsules)

            matches = store.recall(
                project="api",
                task="/tdd database migration",
                files=["src/db/migrations.py"],
                limit=3,
            )

        self.assertEqual(matches, [])

    def test_private_key_block_is_redacted(self) -> None:
        text = (
            "-----BEGIN PRIVATE KEY-----\n"
            "abc123456789\n"
            "-----END PRIVATE KEY-----"
        )

        redacted, count = SecretRedactor().redact(text)

        self.assertEqual(redacted, "<redacted private key>")
        self.assertEqual(count, 1)

    def test_standalone_secret_tokens_are_redacted(self) -> None:
        text = "Rotate sk_live_1234567890abcdef and ghp_1234567890abcdefABCDEF."

        redacted, count = SecretRedactor().redact(text)

        self.assertEqual(
            redacted,
            "Rotate <redacted token> and <redacted token>.",
        )
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
