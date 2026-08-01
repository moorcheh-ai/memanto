from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import chatgpt_to_okf


class ConverterTests(unittest.TestCase):
    def fixture_path(self) -> Path:
        return Path(__file__).parents[1] / "fixtures" / "sample_conversations.json"

    def test_conversion_is_redacted_and_valid(self) -> None:
        conversations = chatgpt_to_okf.load_conversations(self.fixture_path())
        memories = chatgpt_to_okf.make_memories(conversations, redact_output=True)
        self.assertEqual(len(memories), 1)
        self.assertIn("[REDACTED_EMAIL]", memories[0].content)
        self.assertIn("Friday release", memories[0].content)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "okf"
            manifest = chatgpt_to_okf.write_bundle(memories, bundle, redacted=True)
            self.assertEqual(manifest["memory_count"], 1)
            document = next((bundle / "memories" / "event").glob("*.md"))
            self.assertIn("type: event", document.read_text(encoding="utf-8"))
            self.assertTrue((bundle / "index.md").is_file())

    def test_output_names_are_deterministic(self) -> None:
        conversations = chatgpt_to_okf.load_conversations(self.fixture_path())
        memories = chatgpt_to_okf.make_memories(conversations, redact_output=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = chatgpt_to_okf.write_bundle(memories, root / "one", redacted=True)
            second = chatgpt_to_okf.write_bundle(memories, root / "two", redacted=True)
            self.assertEqual(first["entries"][0]["path"], second["entries"][0]["path"])
            self.assertEqual(first["entries"][0]["source_sha256"], second["entries"][0]["source_sha256"])

    def test_invalid_export_shape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conversations.json"
            path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                chatgpt_to_okf.load_conversations(path)

    def test_response_context_follows_the_graph_not_global_timestamp_order(self) -> None:
        conversation = {
            "id": "branching-demo",
            "title": "Branching",
            "mapping": {
                "root": {
                    "parent": None,
                    "message": {
                        "id": "root-message",
                        "author": {"role": "user"},
                        "create_time": 100,
                        "content": {"parts": ["Unrelated root prompt"]},
                    },
                },
                "branch-user": {
                    "parent": "root",
                    "message": {
                        "id": "branch-user-message",
                        "author": {"role": "user"},
                        "create_time": 300,
                        "content": {"parts": ["Correct branch prompt"]},
                    },
                },
                "branch-assistant": {
                    "parent": "branch-user",
                    "message": {
                        "id": "branch-assistant-message",
                        "author": {"role": "assistant"},
                        "create_time": 200,
                        "content": {"parts": ["Correct branch answer"]},
                    },
                },
            },
        }
        memories = chatgpt_to_okf.make_memories([conversation], redact_output=True)
        self.assertEqual(len(memories), 1)
        self.assertIn("Correct branch prompt", memories[0].content)
        self.assertNotIn("Unrelated root prompt", memories[0].content)


if __name__ == "__main__":
    unittest.main()
