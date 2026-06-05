import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claudecode_skills_memanto.bridge import (  # noqa: E402
    MemoryCandidate,
    build_additional_context,
    detect_skill_name,
    distill_memories,
    load_transcript_text,
    main,
    remember_with_memanto,
)


class BridgeTests(unittest.TestCase):
    def test_distills_decisions_preferences_and_project_facts_from_skill_transcript(
        self,
    ):
        transcript = """
        User: /grill-with-docs auth refactor
        Assistant: Decision: keep token refresh inside the auth service because it owns retry policy.
        Assistant: User preference: prefer concise error messages in UI copy.
        Assistant: Codebase fact: API routes live under src/server/routes and use zod schemas.
        Assistant: Random progress chatter that should not become a memory.
        """

        memories = distill_memories(
            transcript,
            skill_name="grill-with-docs",
            project_slug="checkout-api",
        )

        self.assertEqual(
            memories,
            [
                MemoryCandidate(
                    content="keep token refresh inside the auth service because it owns retry policy.",
                    memory_type="decision",
                    confidence=0.95,
                    provenance="observed",
                    source="claude_code:grill-with-docs",
                    tags=("checkout-api", "skill-grill-with-docs", "decision"),
                ),
                MemoryCandidate(
                    content="prefer concise error messages in UI copy.",
                    memory_type="preference",
                    confidence=0.9,
                    provenance="explicit_statement",
                    source="claude_code:grill-with-docs",
                    tags=("checkout-api", "skill-grill-with-docs", "preference"),
                ),
                MemoryCandidate(
                    content="API routes live under src/server/routes and use zod schemas.",
                    memory_type="fact",
                    confidence=0.9,
                    provenance="observed",
                    source="claude_code:grill-with-docs",
                    tags=("checkout-api", "skill-grill-with-docs", "fact"),
                ),
            ],
        )

    def test_builds_user_prompt_expansion_context_for_next_skill(self):
        memories = [
            MemoryCandidate(
                content="keep token refresh inside the auth service because it owns retry policy.",
                memory_type="decision",
                confidence=0.95,
                provenance="observed",
                source="claude_code:grill-with-docs",
                tags=("checkout-api", "skill-grill-with-docs", "decision"),
            ),
            MemoryCandidate(
                content="prefer concise error messages in UI copy.",
                memory_type="preference",
                confidence=0.9,
                provenance="explicit_statement",
                source="claude_code:grill-with-docs",
                tags=("checkout-api", "skill-grill-with-docs", "preference"),
            ),
        ]

        context = build_additional_context(
            memories,
            skill_name="tdd",
            prompt="/tdd implement auth retry tests",
        )

        self.assertIn('<memanto-skill-context skill="tdd">', context)
        self.assertIn("Prompt: /tdd implement auth retry tests", context)
        self.assertIn(
            "- [decision] keep token refresh inside the auth service", context
        )
        self.assertIn(
            "- [preference] prefer concise error messages in UI copy.", context
        )
        self.assertIn("Use these memories as prior engineering context", context)

    def test_cli_supports_dry_run_capture_without_memanto_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            transcript = temp_path / "transcript.jsonl"
            transcript.write_text(
                '{"type":"assistant","message":{"content":[{"type":"text","text":"Decision: use SQLite for the local cache."}]}}\n',
                encoding="utf-8",
            )
            output = temp_path / "memories.jsonl"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "capture",
                        "--transcript",
                        str(transcript),
                        "--skill",
                        "prototype",
                        "--project",
                        "demo-app",
                        "--dry-run-output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("captured 1 memory candidate", stdout.getvalue())
            self.assertIn(
                '"memory_type": "decision"', output.read_text(encoding="utf-8")
            )

    def test_detects_slash_skill_name_from_user_prompt(self):
        self.assertEqual(
            detect_skill_name("/grill-with-docs design the auth cache"),
            "grill-with-docs",
        )
        self.assertEqual(
            detect_skill_name("please run /tdd on the retry behavior"),
            "tdd",
        )
        self.assertIsNone(detect_skill_name("plain prompt without a slash skill"))

    def test_cli_hook_inject_reads_claude_hook_json_from_stdin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            memories = temp_path / "memories.jsonl"
            memories.write_text(
                json_line(
                    MemoryCandidate(
                        content="use zod output schemas for API responses.",
                        memory_type="decision",
                        confidence=0.95,
                        provenance="observed",
                        source="claude_code:grill-with-docs",
                        tags=("checkout-api", "skill-grill-with-docs", "decision"),
                    )
                ),
                encoding="utf-8",
            )
            hook_input = io.StringIO(
                '{"hook_event_name":"UserPromptSubmit","prompt":"/tdd add bounty endpoint tests"}'
            )
            stdout = io.StringIO()
            with mock.patch("sys.stdin", hook_input):
                with redirect_stdout(stdout):
                    exit_code = main(["hook-inject", "--memories", str(memories)])

            self.assertEqual(exit_code, 0)
            self.assertIn('<memanto-skill-context skill="tdd">', stdout.getvalue())
            self.assertIn("use zod output schemas", stdout.getvalue())

    def test_cli_hook_inject_supports_user_prompt_expansion_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            memories = temp_path / "memories.jsonl"
            memories.write_text(
                json_line(
                    MemoryCandidate(
                        content="keep checkout tax logic in billing service.",
                        memory_type="decision",
                        confidence=0.95,
                        provenance="observed",
                        source="claude_code:handoff",
                        tags=("checkout-api", "skill-handoff", "decision"),
                    )
                ),
                encoding="utf-8",
            )
            hook_input = io.StringIO(
                json.dumps(
                    {
                        "hook_event_name": "UserPromptExpansion",
                        "command_name": "handoff",
                        "command_args": "billing rules",
                    }
                )
            )
            stdout = io.StringIO()
            with mock.patch("sys.stdin", hook_input):
                with redirect_stdout(stdout):
                    exit_code = main(["hook-inject", "--memories", str(memories)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            output = payload["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "UserPromptExpansion")
            self.assertIn("keep checkout tax logic", output["additionalContext"])
            self.assertIn("Prompt: /handoff billing rules", output["additionalContext"])

    def test_load_transcript_text_reads_common_claude_jsonl_content_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            transcript = Path(temp_dir) / "transcript.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Decision: keep cache local.",
                                        }
                                    ]
                                }
                            }
                        ),
                        json.dumps(
                            {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Codebase fact: hooks live in .claude.",
                                    }
                                ]
                            }
                        ),
                        json.dumps({"text": "User preference: concise summaries."}),
                    ]
                ),
                encoding="utf-8",
            )

            text = load_transcript_text(transcript)

            self.assertIn("Decision: keep cache local.", text)
            self.assertIn("Codebase fact: hooks live in .claude.", text)
            self.assertIn("User preference: concise summaries.", text)

    def test_remember_with_memanto_logs_failures_and_continues(self):
        memories = [
            MemoryCandidate(
                content="first",
                memory_type="decision",
                confidence=0.95,
                provenance="observed",
                source="claude_code:tdd",
                tags=("demo", "skill-tdd", "decision"),
            ),
            MemoryCandidate(
                content="second",
                memory_type="fact",
                confidence=0.9,
                provenance="observed",
                source="claude_code:tdd",
                tags=("demo", "skill-tdd", "fact"),
            ),
        ]
        stderr = io.StringIO()
        completed = subprocess.CompletedProcess(args=["memanto"], returncode=0)
        with mock.patch(
            "subprocess.run",
            side_effect=[
                subprocess.CalledProcessError(1, ["memanto", "remember", "first"]),
                completed,
            ],
        ) as run:
            with redirect_stderr(stderr):
                stored = remember_with_memanto(memories)

        self.assertEqual(stored, 1)
        self.assertIn("memanto remember failed", stderr.getvalue())
        self.assertEqual(run.call_args_list[0].kwargs["timeout"], 30)
        self.assertEqual(run.call_args_list[1].kwargs["timeout"], 30)

    def test_example_artifacts_exist_and_settings_json_is_valid(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "README.md").exists())
        self.assertTrue(
            (root / ".claude" / "skills" / "memanto-skill-companion" / "SKILL.md").exists()
        )

        settings_path = root / ".claude" / "settings.json"
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = payload["hooks"]
        self.assertIn("UserPromptExpansion", hooks)
        self.assertIn("Stop", hooks)


def json_line(memory: MemoryCandidate) -> str:
    from dataclasses import asdict
    import json

    return json.dumps(asdict(memory), sort_keys=True) + "\n"


if __name__ == "__main__":
    unittest.main()
