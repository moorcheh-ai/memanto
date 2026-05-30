"""Claude Code Hooks Integration for Memanto + mattpocock/skills."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from memory_backend import LocalBackend, get_backend
from skill_memory import (
    extract_from_file_references,
    extract_signals,
    format_memory_context,
    post_hook,
    pre_hook,
)


def hook_user_prompt_submit() -> None:
    """Claude Code UserPromptSubmit hook."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    user_message = data.get("user_prompt", "")
    if not user_message:
        return
    context = pre_hook(user_message)
    if context:
        print(context)


def hook_stop() -> None:
    """Claude Code Stop hook."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    transcript = data.get("transcript", "")
    user_message = data.get("last_user_message", "")
    if not transcript:
        return
    post_hook(user_message, transcript)


def hook_post_tool_use() -> None:
    """Claude Code PostToolUse hook."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    tool_name = data.get("tool_name", "")
    tool_input = json.dumps(data.get("tool_input", {}))
    tool_output = data.get("tool_output", "")
    if tool_name in ("Write", "Edit", "MultiEdit"):
        full_text = f"{tool_input}\n{tool_output}"
        skill_name = os.environ.get("MEMANTO_LAST_SKILL")
        backend = get_backend()
        signals = extract_from_file_references(full_text, skill_name)
        for signal in signals:
            try:
                backend.store(signal)
            except Exception:
                pass


_HOOKS = {
    "UserPromptSubmit": hook_user_prompt_submit,
    "Stop": hook_stop,
    "PostToolUse": hook_post_tool_use,
}


def main() -> None:
    hook_name = os.environ.get("CLAUDE_HOOK_NAME", "")
    handler = _HOOKS.get(hook_name)
    if handler:
        handler()
    else:
        print(f"Unknown hook: {hook_name}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
