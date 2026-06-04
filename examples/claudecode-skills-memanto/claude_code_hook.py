#!/usr/bin/env python3
"""
claude_code_hook.py — Claude Code integration via its hook system.

Claude Code supports hooks that run before/after tool calls.
This script can be configured as a PreToolUse/PostToolUse hook to
automatically inject Memanto context and store learnings.

Setup in your Claude Code settings (~/.claude/settings.json):

{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Write|Edit",
      "hook": "python /path/to/claude_code_hook.py pre"
    }],
    "PostToolUse": [{
      "matcher": "Bash|Write|Edit",
      "hook": "python /path/to/claude_code_hook.py post"
    }]
  }
}

Or for a specific project, add to .claude/settings.json in the repo.
"""

from __future__ import annotations

import json
import os
import sys
import re
import tempfile
from pathlib import Path

from memanto_skill_hook.memory import SkillMemory

# ---------------------------------------------------------------------------
# Hook state file — stores the pre-hook context for the post-hook to consume
# ---------------------------------------------------------------------------
_STATE_DIR = Path(tempfile.gettempdir())
_STATE_PREFIX = "memanto_hook_state_"


def _state_file() -> Path:
    """Return a PID-scoped state file to avoid cross-process collisions."""
    return _STATE_DIR / f"{_STATE_PREFIX}{os.getpid()}.json"


def _save_state(data: dict) -> None:
    _state_file().write_text(json.dumps(data))


def _load_state() -> dict:
    sf = _state_file()
    if sf.exists():
        return json.loads(sf.read_text())
    return {}


def _detect_skill_from_cwd() -> str:
    """Infer the active skill from the working directory or env."""
    # Check if a skill env var is set (you can export this in your wrapper)
    skill = os.environ.get("MEMANTO_ACTIVE_SKILL", "")
    if skill:
        return skill
    # Default: treat as general coding
    return "/code"


def _extract_file_path(tool_input: dict) -> str:
    """Extract the file path from a Claude Code tool input."""
    for key in ("file_path", "path", "filePath", "command"):
        val = tool_input.get(key, "")
        if val and isinstance(val, str):
            return val
    return ""


def pre_hook() -> None:
    """PreToolUse hook — inject Memanto context."""
    try:
        stdin_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    tool_name = stdin_data.get("tool_name", "")
    tool_input = stdin_data.get("tool_input", {})
    file_path = _extract_file_path(tool_input)
    skill = _detect_skill_from_cwd()

    mem = SkillMemory()
    ctx = mem.on_skill_start(
        skill_name=skill,
        file_path=file_path,
        task_description=f"Using {tool_name} on {file_path}",
    )

    # Save state for post-hook
    _save_state({
        "skill": skill,
        "file_path": file_path,
        "tool_name": tool_name,
    })

    if ctx:
        # Output the context to stdout — Claude Code will read it
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": ctx,
            }
        }
        print(json.dumps(output))


def post_hook() -> None:
    """PostToolUse hook — store learnings from the tool output."""
    try:
        stdin_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    state = _load_state()
    if not state:
        return

    tool_output = stdin_data.get("tool_output", "")
    if isinstance(tool_output, list):
        tool_output = " ".join(str(x) for x in tool_output)
    elif not isinstance(tool_output, str):
        tool_output = str(tool_output)

    # Sanitize: strip ANSI escape codes and control characters
    tool_output = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", tool_output)
    tool_output = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", tool_output)

    # Only store if there's meaningful output
    if len(tool_output.strip()) < 20:
        return

    # Truncate very long outputs
    if len(tool_output) > 2000:
        tool_output = tool_output[:1997] + "..."

    mem = SkillMemory()
    mem.on_skill_complete(
        skill_name=state.get("skill", "/code"),
        summary=f"Tool: {state.get('tool_name', 'unknown')}\n\n{tool_output}",
        file_path=state.get("file_path", ""),
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    if mode == "pre":
        pre_hook()
    elif mode == "post":
        post_hook()


if __name__ == "__main__":
    main()
