from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from context_capsules import (
    Capsule,
    CapsuleExtractor,
    LocalCapsuleStore,
    SecretRedactor,
    format_context_block,
    score_capsule,
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
        text = "-----BEGIN PRIVATE KEY-----\nabc123456789\n-----END PRIVATE KEY-----"

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

    def test_recall_with_tied_scores_returns_without_raising(self) -> None:
        # Two unrelated, un-matchable Capsule objects get a tied score of 0;
        # the prior `sorted(scored, reverse=True)` could TypeError because
        # Capsule is not orderable and Python's sort may need to break the
        # tie by comparing Capsule instances. Use many tied capsules so
        # Timsort must invoke the tiebreaker at least once.
        with TemporaryDirectory() as temp_dir:
            store = LocalCapsuleStore(Path(temp_dir) / "capsules.jsonl")
            store.append_many(
                [
                    Capsule(
                        kind="context",
                        content=f"Quokka variant {idx} thrive in dense coastal thickets without predators.",
                        project="fauna-survey",
                        files=["docs/fauna.md"],
                        source_skill="/handoff",
                        session_id=f"s{idx}",
                        tags=["fauna"],
                        confidence=0.9,
                        created_at=f"2026-01-01T00:00:0{idx % 10}+00:00",
                    )
                    for idx in range(8)
                ]
            )

            # An unrelated recall produces many tied scores for the capsules.
            matches = store.recall(
                project="finance",
                task="/tdd stripe webhook idempotency",
                files=["app/billing/invoices.py"],
                limit=5,
            )

        # The filter `score > 0` strips all tied zero-score rows; the test
        # is just to ensure no TypeError bubbles out of the sort comparator.
        self.assertEqual(matches, [])

    def test_score_capsule_returns_zero_for_unrelated_query(self) -> None:
        # Sanity: confirms the tied-score fixture above actually ties at 0.
        capsule = Capsule(
            kind="context",
            content="Quokka colonies thrive in dense coastal thickets without predators.",
            project="fauna-survey",
            files=["docs/fauna.md"],
            source_skill="/handoff",
            session_id="s1",
            tags=["fauna"],
            confidence=0.9,
            created_at="2026-01-01T00:00:00+00:00",
        )

        score = score_capsule(
            capsule,
            project="finance",
            task="/tdd stripe webhook idempotency",
            files=["app/billing/invoices.py"],
        )

        self.assertEqual(score, 0.0)


if __name__ == "__main__":
    unittest.main()
