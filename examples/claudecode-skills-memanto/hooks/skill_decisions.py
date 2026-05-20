#!/usr/bin/env python3
"""
Claude Code hook: PostToolUse (optional)
========================================

Lightweight tagger. When a tool runs after a recent `/skill-name` invocation,
this hook annotates the running session with the skill name so that
distill_session.py at end-of-session can tag stored memories with the
originating skill.

The annotation is written to a session-local state file (one per
transcript_path) so distill_session can read it back.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _memanto_common import get_logger, parse_hook_input  # noqa: E402

LOG = get_logger("skill_decisions")

STATE_DIR = Path.home() / ".claude" / "hooks" / "memanto" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SKILL_INVOCATION_PATTERN = re.compile(r"(?:^|\s)/([a-z][a-z0-9-]{1,40})\b")


def session_state_path(transcript_path: str) -> Path:
    safe = transcript_path.replace("/", "_").replace("\\", "_").replace(":", "_")
    return STATE_DIR / f"{safe}.json"


def main() -> int:
    ctx = parse_hook_input()
    if ctx is None:
        return 0

    user_prompt = ctx.payload.get("prompt") or ""
    transcript_path = ctx.payload.get("transcript_path")
    if not transcript_path or not user_prompt:
        return 0

    # Find skill invocations in the most-recent user prompt
    matches = SKILL_INVOCATION_PATTERN.findall(user_prompt)
    if not matches:
        return 0

    skill = matches[-1]  # the last-mentioned skill wins
    state_path = session_state_path(transcript_path)

    try:
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            data = {"skills": []}
    except (OSError, json.JSONDecodeError):
        data = {"skills": []}

    if skill not in data["skills"]:
        data["skills"].append(skill)
        try:
            state_path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            LOG.info("Recorded skill invocation: /%s", skill)
        except OSError as exc:
            LOG.error("Failed to write state file: %s", exc)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        LOG.exception("Unexpected error: %s", exc)
        sys.exit(0)
