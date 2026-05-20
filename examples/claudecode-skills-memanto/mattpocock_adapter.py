#!/usr/bin/env python3
"""Generate shell wrappers for mattpocock/skills-style commands."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path


WRAPPER_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME={skill_name}
PROMPT="${{*:-}}"
TRANSCRIPT_FILE="$(mktemp)"

MEMANTO_SKILL_CONTEXT="$(python "$(dirname "$0")/../skill_memory.py" before --skill "$SKILL_NAME" --prompt "$PROMPT")"
export MEMANTO_SKILL_CONTEXT
printf '%s\n' "$MEMANTO_SKILL_CONTEXT"

# Replace this echo with the real skill executable, for example:
# claude "$SKILL_NAME $PROMPT"
echo "Running $SKILL_NAME with prompt: $PROMPT" | tee "$TRANSCRIPT_FILE"

python "$(dirname "$0")/../skill_memory.py" after \
  --skill "$SKILL_NAME" \
  --prompt "$PROMPT" \
  --transcript "$TRANSCRIPT_FILE"
"""


def write_wrappers(skills: list[str], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for skill in skills:
        name = skill.strip()
        filename = name.strip("/").replace("/", "-") or "skill"
        path = out / filename
        path.write_text(
            WRAPPER_TEMPLATE.format(skill_name=shlex.quote(name)),
            encoding="utf-8",
        )
        path.chmod(0o755)
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", nargs="+", required=True)
    parser.add_argument("--out", default=".skill-wrappers")
    args = parser.parse_args()

    for path in write_wrappers(args.skills, Path(args.out)):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
