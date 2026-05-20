"""Generate shell wrappers for Claude Code skill commands."""

from __future__ import annotations

from pathlib import Path


SKILLS = {
    "grill-with-docs": "claude /grill-with-docs \"$@\"",
    "tdd": "claude /tdd \"$@\"",
    "handoff": "claude /handoff \"$@\"",
}


def wrapper_script(skill: str, command: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

TRANSCRIPT="${{MEMANTO_SKILL_TRANSCRIPT:-.memanto-{skill}-transcript.txt}}"
TASK="$*"

python "$(dirname "$0")/skill_memory.py" pre --skill "{skill}" --task "$TASK"
{command} 2>&1 | tee "$TRANSCRIPT"
python "$(dirname "$0")/skill_memory.py" post --skill "{skill}" --transcript-file "$TRANSCRIPT"
"""


def write_wrappers(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for skill, command in SKILLS.items():
        path = output_dir / skill
        path.write_text(wrapper_script(skill, command), encoding="utf-8")
        path.chmod(0o755)
        written.append(path)
    return written

