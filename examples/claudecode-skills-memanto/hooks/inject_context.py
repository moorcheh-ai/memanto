#!/usr/bin/env python3
"""
Claude Code UserPromptSubmit hook — injects relevant Memanto memories into
the conversation context before Claude processes each user message.

Reads the hook payload from stdin (JSON), queries Memanto for memories
relevant to the incoming user prompt, and outputs them as a JSON object
that Claude Code merges into the system context.

Hook event schema (UserPromptSubmit):
  {
    "session_id": "...",
    "cwd": "...",
    "hook_event_name": "UserPromptSubmit",
    "prompt": "the user's message",
    ...
  }

Return value (printed to stdout as JSON):
  {
    "additionalSystemPrompt": "Remembered preferences:\\n- ..."
  }

Usage (hooks entry in ~/.claude/settings.json):
  {
    "hooks": {
      "UserPromptSubmit": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 /path/to/inject_context.py"
            }
          ]
        }
      ]
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_here))

from memory_tools import recall  # noqa: E402

MAX_MEMORIES = 5
MIN_SCORE = 0.65  # Minimum similarity score to include a memory


def main() -> None:
    payload: dict = {}
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    cwd = payload.get("cwd") or os.getcwd()
    prompt = payload.get("prompt", "").strip()

    if not prompt:
        return  # Nothing to query against

    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        return  # Silently skip — no API key configured

    try:
        memories = recall(
            query=prompt,
            top_k=MAX_MEMORIES,
            project_path=cwd,
            api_key=api_key,
        )
    except Exception:
        return  # Never crash Claude Code

    if not memories:
        return

    # Filter by relevance score
    relevant = []
    for mem in memories:
        score = 0.0
        if isinstance(mem, dict):
            score = float(mem.get("score", mem.get("similarity", 0)))
            text = mem.get("text") or mem.get("content") or ""
        else:
            text = str(mem)
        if score >= MIN_SCORE and text:
            relevant.append(text)

    if not relevant:
        return

    # Build the additional system prompt fragment
    block = "Remembered developer preferences for this project:\n"
    for i, mem_text in enumerate(relevant, 1):
        # Strip the [TYPE] prefix and truncate for readability
        clean = mem_text.split("\n\n")[0].removeprefix("[PREFERENCE] ").removeprefix(
            "[DECISION] ").removeprefix("[FACT] ").removeprefix("[PATTERN] ").removeprefix(
            "[CONSTRAINT] ")
        block += f"- {clean[:200]}\n"

    output = {"additionalSystemPrompt": block.strip()}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
