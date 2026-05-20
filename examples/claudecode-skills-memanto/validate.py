from __future__ import annotations

import tempfile
from pathlib import Path

from claude_skill_memory import handle_hook_event


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when an expected condition is false."""

    if not condition:
        raise RuntimeError(message)


def main() -> int:
    """Exercise the credential-free hook flow end to end."""

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
        require(
            stored.get("stored") == 3,
            f"expected 3 stored memories, got {stored.get('stored')}",
        )
        for expected in (
            "Redis streams",
            "pytest fixtures",
            "generated SDK clients",
        ):
            require(expected in context, f"missing recalled context: {expected}")
    print("credential-free Claude Code hook validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
