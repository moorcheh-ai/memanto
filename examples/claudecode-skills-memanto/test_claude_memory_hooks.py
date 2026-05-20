import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from claude_memory_hooks import (
    HookEvent,
    LocalMemoryStore,
    build_context,
    capture_memories,
    distill_memories,
    main,
)


class LocalMemoryStoreTest(unittest.TestCase):
    def test_search_prioritizes_matching_tags_and_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalMemoryStore(Path(temp_dir) / "memory.jsonl")
            store.add(
                {
                    "type": "decision",
                    "title": "Use repository adapters",
                    "content": "Decision: keep billing code behind repository adapters.",
                    "confidence": 0.9,
                    "tags": ["billing", "architecture"],
                    "source_event": "Stop",
                    "session_id": "s1",
                    "cwd": "/work/acme",
                }
            )
            store.add(
                {
                    "type": "preference",
                    "title": "Prefer compact docs",
                    "content": "Preference: keep README examples short.",
                    "confidence": 0.7,
                    "tags": ["docs"],
                    "source_event": "Stop",
                    "session_id": "s1",
                    "cwd": "/work/acme",
                }
            )

            matches = store.search(
                "billing adapter implementation",
                cwd="/work/acme",
                limit=1,
            )

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["title"], "Use repository adapters")


class DistillationTest(unittest.TestCase):
    def test_distills_engineering_decisions_preferences_and_instructions(self):
        memories = distill_memories(
            """
            Decision: keep writes behind the PartnerRepository boundary.
            Preference: use small focused Playwright tests for browser regressions.
            Never commit local planning docs to public branches.
            Caveat: the auth seed only exists after make db-bootstrap.
            """,
            source_event="Stop",
            session_id="s2",
            cwd="/repo/app",
        )

        by_type = {memory["type"]: memory for memory in memories}

        self.assertIn("decision", by_type)
        self.assertIn("preference", by_type)
        self.assertIn("instruction", by_type)
        self.assertIn("context", by_type)
        self.assertGreaterEqual(by_type["instruction"]["confidence"], 0.9)
        self.assertIn("PartnerRepository", by_type["decision"]["content"])


class HookContextTest(unittest.TestCase):
    def test_build_context_uses_user_prompt_submit_additional_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalMemoryStore(Path(temp_dir) / "memory.jsonl")
            store.add(
                {
                    "type": "instruction",
                    "title": "Keep docs local",
                    "content": "Never commit local planning docs to public branches.",
                    "confidence": 0.95,
                    "tags": ["docs", "git"],
                    "source_event": "Stop",
                    "session_id": "old",
                    "cwd": "/repo/app",
                }
            )
            event = HookEvent.from_dict(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "new",
                    "cwd": "/repo/app",
                    "prompt": "Prepare docs and branch for a GitHub PR",
                }
            )

            payload = build_context(event, store, limit=3)

            self.assertEqual(
                payload["hookSpecificOutput"]["hookEventName"],
                "UserPromptSubmit",
            )
            self.assertIn(
                "Never commit local planning docs",
                payload["hookSpecificOutput"]["additionalContext"],
            )
            self.assertNotIn("decision", payload)


class CaptureTest(unittest.TestCase):
    def test_capture_reads_transcript_and_stores_distilled_memories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "user",
                                "message": {
                                    "content": "Use the local auth seed path.",
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Decision: auth tests must run after db-bootstrap.",
                                        }
                                    ]
                                },
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            store = LocalMemoryStore(Path(temp_dir) / "memory.jsonl")
            event = HookEvent.from_dict(
                {
                    "hook_event_name": "Stop",
                    "session_id": "s3",
                    "cwd": "/repo/app",
                    "transcript_path": str(transcript),
                }
            )

            stored = capture_memories(event, store)

            self.assertEqual(stored, 1)
            self.assertIn(
                "db-bootstrap",
                store.search("auth tests bootstrap", cwd="/repo/app", limit=1)[0][
                    "content"
                ],
            )


class CliTest(unittest.TestCase):
    def test_cli_inject_outputs_json_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "memory.jsonl"
            LocalMemoryStore(store_path).add(
                {
                    "type": "decision",
                    "title": "Use route loaders",
                    "content": "Decision: prefer route loaders for dashboard data.",
                    "confidence": 0.86,
                    "tags": ["dashboard"],
                    "source_event": "Stop",
                    "session_id": "old",
                    "cwd": "/repo/app",
                }
            )
            event = {
                "hook_event_name": "UserPromptExpansion",
                "session_id": "new",
                "cwd": "/repo/app",
                "command_name": "tdd",
                "command_args": "dashboard route loader",
                "prompt": "/tdd dashboard route loader",
            }
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(
                    ["inject", "--backend", "local", "--store", str(store_path)],
                    stdin=json.dumps(event),
                )

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(
                payload["hookSpecificOutput"]["hookEventName"],
                "UserPromptExpansion",
            )
            self.assertIn(
                "prefer route loaders",
                payload["hookSpecificOutput"]["additionalContext"],
            )


if __name__ == "__main__":
    unittest.main()
