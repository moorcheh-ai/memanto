"""
hooks/on_stop.py
================
Claude Code Stop hook — distills and stores engineering decisions after skill.

Called when Claude Code finishes a response.
Extracts architectural decisions, preferences, and constraints from the
transcript and stores them to Memanto via official moorcheh-sdk.

Key differentiator: uses answer.generate() (LLM) to extract memories,
not just regex pattern matching. The LLM reads the full transcript and
identifies what's worth remembering.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks._common import (
    detect_skill,
    extract_decisions_with_llm,
    extract_files_from_transcript,
    get_client,
    write_hook_output,
)

# Guard against double-distillation within same session
_GUARD_FILE = Path(".memanto-stop-active")


def main() -> int:
    """Stop hook entrypoint."""
    if _GUARD_FILE.exists():
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    transcript = payload.get("transcript", "")
    skill = detect_skill(payload)
    cwd = payload.get("cwd", os.getcwd())

    if not transcript or len(transcript.strip()) < 50:
        write_hook_output({"stored": 0, "skill": skill})
        return 0

    try:
        client = get_client()
    except ValueError:
        write_hook_output({"stored": 0, "reason": "no api key"})
        return 0

    _GUARD_FILE.touch()
    try:
        files = extract_files_from_transcript(transcript)
        memories = extract_decisions_with_llm(client, transcript, skill, files)

        stored = 0
        for memory in memories:
            result = client.store(
                content=memory["content"],
                memory_type=memory.get("type", "observation"),
                skill=skill,
                tags=memory.get("tags", []) + [skill, Path(cwd).name],
                confidence=memory.get("confidence", 0.8),
            )
            if result.get("id"):
                stored += 1

        write_hook_output({"stored": stored, "skill": skill, "memories": memories})
    finally:
        _GUARD_FILE.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
