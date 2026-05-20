import json
import tempfile
import unittest
from pathlib import Path

from claude_skill_memory import handle_hook_event


class ClaudeSkillMemoryHookTests(unittest.TestCase):
    def test_stop_event_distills_and_redacts_durable_engineering_memory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "memory.jsonl"
            event = {
                "hook_event_name": "Stop",
                "cwd": "/repo",
                "transcript": (
                    "We decided to use server-side validation for checkout forms.\n"
                    "Always keep generated API clients out of source control.\n"
                    "OPENAI_API_KEY=sk-secret-should-not-leak\n"
                ),
            }

            result = handle_hook_event(event, store)

            self.assertEqual(result["stored"], 2)
            records = [json.loads(line) for line in store.read_text().splitlines()]
            self.assertEqual(
                [record["kind"] for record in records], ["decision", "instruction"]
            )
            serialized = json.dumps(records)
            self.assertIn("server-side validation", serialized)
            self.assertIn("generated API clients", serialized)
            self.assertNotIn("sk-secret-should-not-leak", serialized)

    def test_user_prompt_submit_returns_claude_additional_context_from_memories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "memory.jsonl"
            stop_event = {
                "hook_event_name": "Stop",
                "cwd": "/repo",
                "transcript": (
                    "Decision: use Redis for retry queues in billing workers.\n"
                    "Prefer pytest fixtures over shared mutable globals.\n"
                ),
            }
            handle_hook_event(stop_event, store)

            prompt_event = {
                "hook_event_name": "UserPromptSubmit",
                "cwd": "/repo",
                "prompt": "Use /tdd to add retry queue tests for billing",
                "tool_input": {"file_path": "tests/test_billing_retries.py"},
            }
            result = handle_hook_event(prompt_event, store)

            self.assertFalse(result["suppressOutput"])
            additional_context = result["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Memanto engineering memory", additional_context)
            self.assertIn("Redis", additional_context)
            self.assertIn("pytest fixtures", additional_context)


if __name__ == "__main__":
    unittest.main()
