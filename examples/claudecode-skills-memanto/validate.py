from __future__ import annotations

import tempfile
from pathlib import Path

from claude_skill_memory import handle_hook_event


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Path(tmpdir) / "memory.jsonl"
        stored = handle_hook_event(
            {
                "hook_event_name": "Stop",
                "cwd": "/workspace/shop",
                "skill": "grill-with-docs",
                "transcript": (
                    "Decision: use Redis streams for billing retries.\n"
                    "Prefer pytest fixtures over mutable module globals.\n"
                    "Never commit generated SDK clients.\n"
                ),
            },
            store,
        )
        recalled = handle_hook_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": "/workspace/shop",
                "prompt": "Use /tdd to add billing retry tests",
                "tool_input": {"file_path": "tests/test_billing_retries.py"},
            },
            store,
        )
        context = recalled["hookSpecificOutput"]["additionalContext"]
        assert stored["stored"] == 3
        assert "Redis streams" in context
        assert "pytest fixtures" in context
        assert "generated SDK clients" in context
    print("credential-free Claude Code hook validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
