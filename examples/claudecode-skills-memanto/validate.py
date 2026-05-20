"""Credential-free validation for the Claude Code skills Memanto hook example."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOOK = ROOT / "claude_memory_hooks.py"


def run() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = Path(temp_dir) / "memory.jsonl"
        transcript = Path(temp_dir) / "transcript.jsonl"
        transcript.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "content": "Decision: keep skill memory in Memanto, not per-command temp files."
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "content": "Never repeat the repository's docs hygiene rules manually."
                            },
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )

        capture_event = {
            "hook_event_name": "Stop",
            "session_id": "validation-1",
            "cwd": str(ROOT),
            "transcript_path": str(transcript),
        }
        capture = subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "capture",
                "--backend",
                "local",
                "--store",
                str(store),
            ],
            input=json.dumps(capture_event),
            capture_output=True,
            text=True,
            check=True,
        )
        capture_payload = json.loads(capture.stdout)
        assert capture_payload["stored_memories"] == 2, capture.stdout

        inject_event = {
            "hook_event_name": "UserPromptExpansion",
            "session_id": "validation-2",
            "cwd": str(ROOT),
            "command_name": "tdd",
            "command_args": "docs hygiene memory",
            "prompt": "/tdd docs hygiene memory",
        }
        inject = subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "inject",
                "--backend",
                "local",
                "--store",
                str(store),
            ],
            input=json.dumps(inject_event),
            capture_output=True,
            text=True,
            check=True,
        )
        inject_payload = json.loads(inject.stdout)
        context = inject_payload["hookSpecificOutput"]["additionalContext"]
        assert "Never repeat the repository" in context, context
        assert "hookSpecificOutput" in inject_payload

    print("credential-free validation passed")


if __name__ == "__main__":
    run()
