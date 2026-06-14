"""
hooks/on_prompt.py
==================
Claude Code UserPromptSubmit hook — injects engineering profile before each prompt.

Called before every user message is sent to Claude.
Detects skill from prompt content and injects relevant memories.

This enables dynamic context injection — if you switch skills mid-session,
the hook automatically recalls the right engineering memories.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks._common import (
    detect_skill,
    extract_files_from_prompt,
    get_client,
    render_profile,
    write_hook_output,
)


def main() -> int:
    """UserPromptSubmit hook entrypoint."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    prompt = payload.get("prompt", "")
    skill = detect_skill(payload) or detect_skill_from_text(prompt)
    cwd = payload.get("cwd", os.getcwd())
    project = Path(cwd).name
    files = extract_files_from_prompt(prompt)

    try:
        client = get_client()
    except ValueError:
        write_hook_output({"memanto_context": "", "injected": False})
        return 0

    # Build semantic query from skill + task context + files
    file_context = " ".join(Path(f).stem for f in files[:3])
    query = f"{skill} {project} {file_context} decisions preferences".strip()

    memories = client.recall(query=query, skill=skill, limit=5)
    profile = render_profile(skill, memories)

    write_hook_output({
        "memanto_context": profile,
        "skill": skill,
        "injected": bool(memories),
        "memory_count": len(memories),
    })

    if profile:
        print(profile)

    return 0


def detect_skill_from_text(text: str) -> str:
    """Detect mattpocock skill name from prompt text."""
    skills = [
        "/tdd", "/grill-with-docs", "/grill-me", "/handoff",
        "/improve-codebase-architecture", "/diagnose",
        "/to-issues", "/to-prd",
    ]
    lowered = text.lower()
    for skill in skills:
        if skill in lowered or skill.lstrip("/") in lowered:
            return skill
    return "general"


if __name__ == "__main__":
    sys.exit(main())
