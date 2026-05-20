"""Generate lightweight wrappers for mattpocock-style skill commands."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

DEFAULT_SKILLS = ("/grill-with-docs", "/tdd", "/handoff")


def wrapper_script(skill: str, target_command: str) -> str:
    quoted_skill = shlex.quote(skill)
    quoted_target = shlex.quote(target_command)
    return f"""#!/usr/bin/env bash
set -euo pipefail

TASK="${{*:-Run {skill}}}"
RUN_DIR="${{SKILL_MEMORY_RUN_DIR:-.memanto-skill-memory/runs}}"
mkdir -p "$RUN_DIR"

python "$(dirname "$0")/skill_memory.py" pre-skill \\
  --skill {quoted_skill} \\
  --task "$TASK" \\
  --cwd "$PWD"

OUTPUT_FILE="$(mktemp)"
set +e
{quoted_target} "$@" 2>&1 | tee "$OUTPUT_FILE"
STATUS=${{PIPESTATUS[0]}}
set -e

RUN_JSON="$RUN_DIR/{skill.strip('/').replace('/', '-')}-$(date -u +%Y%m%dT%H%M%SZ).json"
python - "$RUN_JSON" {quoted_skill} "$TASK" "$PWD" "$OUTPUT_FILE" <<'PY'
import json
import sys
from pathlib import Path

run_json, skill, task, cwd, output_file = sys.argv[1:]
Path(run_json).write_text(json.dumps({{
    "skill": skill,
    "task": task,
    "cwd": cwd,
    "files": [],
    "output": Path(output_file).read_text(encoding="utf-8", errors="replace"),
}}, indent=2) + "\\n", encoding="utf-8")
PY

python "$(dirname "$0")/skill_memory.py" post-skill --run-json "$RUN_JSON"
exit "$STATUS"
"""


def generate(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for skill in args.skills:
        name = skill.strip("/").replace("/", "-")
        path = output_dir / f"{name}-with-memanto"
        path.write_text(wrapper_script(skill, args.target_command), encoding="utf-8")
        path.chmod(0o755)
        manifest[skill] = str(path)
    print(json.dumps(manifest, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=".memanto-skill-memory/bin")
    parser.add_argument("--target-command", default="claude")
    parser.add_argument("--skills", nargs="*", default=list(DEFAULT_SKILLS))
    args = parser.parse_args()
    return generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
