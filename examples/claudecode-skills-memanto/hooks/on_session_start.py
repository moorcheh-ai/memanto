"""
hooks/on_session_start.py
=========================
Claude Code SessionStart hook — injects engineering profile at session open.

Registered in .claude/settings.json as a SessionStart hook.
Called once when Claude Code opens a new session.

What it does:
  1. Detects which skill is being invoked from the transcript/prompt
  2. Recalls relevant engineering memories from Memanto
  3. Injects them as MEMANTO_CONTEXT env var for Claude to read
  4. Uses RAG answer.generate() for synthesized context, not just raw recall

Install:
    python install.py

Manual registration in .claude/settings.json:
    {
      "hooks": {
        "SessionStart": [{"command": "python hooks/on_session_start.py"}]
      }
    }
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow import from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks._common import (
    detect_skill,
    get_client,
    render_profile,
    write_hook_output,
)


def main() -> int:
    """SessionStart hook entrypoint."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    skill = detect_skill(payload)
    cwd = payload.get("cwd", os.getcwd())
    project = Path(cwd).name

    try:
        client = get_client()
    except ValueError:
        # No API key — skip silently, don't block Claude Code
        write_hook_output({"memanto_context": "", "skill": skill})
        return 0

    # Recall relevant memories for this skill + project
    query = f"{skill} {project} engineering decisions preferences".strip()
    memories = client.recall(query=query, skill=skill, limit=6)

    # RAG answer for synthesized context (key differentiator vs CLI wrappers)
    rag_context = ""
    if memories:
        rag_question = (
            f"What engineering decisions, constraints, and preferences are most "
            f"relevant for the {skill} skill working on the {project} project?"
        )
        rag_context = client.answer(rag_question)

    profile = render_profile(skill, memories, rag_context)
    write_hook_output({"memanto_context": profile, "skill": skill})

    # Print to stdout so Claude Code sees it in context
    if profile:
        print(profile)

    return 0


if __name__ == "__main__":
    sys.exit(main())
