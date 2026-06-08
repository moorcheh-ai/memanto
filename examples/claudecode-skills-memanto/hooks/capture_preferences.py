#!/usr/bin/env python3
"""
Claude Code stop hook — captures engineering preferences from the current session.

Installed as a `stop` hook in ~/.claude/settings.json.
Reads the Claude Code hook payload from stdin (JSON) and extracts any
architectural decisions, tool choices, or coding preferences that were
expressed during the session, then stores them in Memanto.

Hook event schema (PostToolUse / Stop):
  {
    "session_id": "...",
    "transcript_path": "...",
    "cwd": "...",
    "hook_event_name": "Stop",
    ...
  }

Usage (hooks entry in ~/.claude/settings.json):
  {
    "hooks": {
      "Stop": [
        {
          "matcher": "",
          "hooks": [
            {
              "type": "command",
              "command": "python3 /path/to/capture_preferences.py"
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

# Resolve project root to find memory_tools
_here = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_here))

from memory_tools import remember  # noqa: E402


PREFERENCE_PATTERNS = [
    # Tool / language choices
    ("prefer", "preference"),
    ("always use", "preference"),
    ("don't use", "preference"),
    ("avoid", "preference"),
    # Architectural decisions
    ("decided to", "decision"),
    ("architecture:", "decision"),
    ("pattern:", "pattern"),
    # Constraints / rules
    ("rule:", "constraint"),
    ("constraint:", "constraint"),
    ("never ", "constraint"),
    # Facts about the project
    ("api endpoint", "fact"),
    ("database is", "fact"),
    ("deployed to", "fact"),
]


def extract_preferences(text: str) -> list[dict]:
    """
    Heuristic extraction: look for sentences containing preference/decision markers.
    Returns a list of {title, content, memory_type} dicts.
    """
    preferences = []
    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if len(line) < 20:
            continue
        for pattern, memory_type in PREFERENCE_PATTERNS:
            if pattern.lower() in line.lower():
                # Title = first 80 chars; content = full line
                title = line[:80].rstrip(".,;:")
                preferences.append({
                    "title": title,
                    "content": line,
                    "memory_type": memory_type,
                })
                break  # one type per line

    # Deduplicate by title
    seen: set[str] = set()
    result = []
    for p in preferences:
        if p["title"] not in seen:
            seen.add(p["title"])
            result.append(p)
    return result


def main() -> None:
    payload: dict = {}
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass  # Hook called with empty stdin — skip silently

    cwd = payload.get("cwd") or os.getcwd()
    transcript_path = payload.get("transcript_path", "")

    # Read the transcript file to find content from this session
    content_to_scan = ""
    if transcript_path and Path(transcript_path).exists():
        try:
            raw = Path(transcript_path).read_text(errors="replace")
            # JSONL — each line is a message event; extract assistant text
            for line in raw.splitlines():
                try:
                    event = json.loads(line)
                    msg = event.get("message", {})
                    if msg.get("role") == "assistant":
                        for block in msg.get("content", []):
                            if isinstance(block, dict) and block.get("type") == "text":
                                content_to_scan += block.get("text", "") + "\n"
                except (json.JSONDecodeError, AttributeError):
                    continue
        except OSError:
            pass

    if not content_to_scan.strip():
        return  # Nothing to extract

    preferences = extract_preferences(content_to_scan)
    if not preferences:
        return

    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        return  # Skip silently if no API key configured

    stored = 0
    for pref in preferences[:10]:  # Cap at 10 per session to avoid noise
        try:
            remember(
                title=pref["title"],
                content=pref["content"],
                memory_type=pref["memory_type"],
                tags=["claude-code", "auto-captured"],
                project_path=cwd,
                api_key=api_key,
            )
            stored += 1
        except Exception:
            pass  # Never crash Claude Code

    if stored:
        print(f"[memanto] Captured {stored} preference(s) to project memory.", file=sys.stderr)


if __name__ == "__main__":
    main()
