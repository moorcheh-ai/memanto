"""Generate wrappers for mattpocock-style developer skill commands."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_SKILLS = (
    "grill-with-docs",
    "tdd",
    "handoff",
    "triage",
    "diagnose",
)


@dataclass(frozen=True)
class SkillWrapperSpec:
    skill: str
    original_command: str
    context_file: str
    transcript_file: str


def default_specs() -> list[SkillWrapperSpec]:
    return [
        SkillWrapperSpec(
            skill=skill,
            original_command=skill,
            context_file=f".memanto/{skill}-context.md",
            transcript_file=f".memanto/{skill}-transcript.md",
        )
        for skill in DEFAULT_SKILLS
    ]


def render_wrapper(spec: SkillWrapperSpec) -> str:
    quoted_skill = shlex.quote(spec.skill)
    quoted_context = shlex.quote(spec.context_file)
    quoted_transcript = shlex.quote(spec.transcript_file)
    quoted_command = shlex.quote(spec.original_command)
    return f"""#!/usr/bin/env bash
set -euo pipefail

TASK="${{1:-}}"
WORKSPACE="${{MEMANTO_WORKSPACE:-default}}"
mkdir -p "$(dirname {quoted_context})"

python3 skill_memory.py before \\
  --skill {quoted_skill} \\
  --task "$TASK" \\
  --workspace "$WORKSPACE" > {quoted_context}

echo "Memanto context written to {quoted_context}" >&2

set +e
{quoted_command} "$@" 2>&1 | tee {quoted_transcript}
STATUS=${{PIPESTATUS[0]}}
set -e

python3 skill_memory.py after \\
  --skill {quoted_skill} \\
  --task "$TASK" \\
  --workspace "$WORKSPACE" \\
  --transcript {quoted_transcript} >/dev/null

exit "$STATUS"
"""


def write_wrappers(out_dir: Path, specs: list[SkillWrapperSpec]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in specs:
        path = out_dir / spec.skill
        path.write_text(render_wrapper(spec), encoding="utf-8")
        path.chmod(0o755)
        written.append(path)
    manifest = {
        "description": "Memanto lifecycle wrappers for developer skills",
        "wrappers": [asdict(spec) for spec in specs],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(out_dir / "manifest.json")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="write wrapper scripts")
    generate.add_argument("--out", default=".memanto-wrappers")
    args = parser.parse_args(argv)

    if args.command == "generate":
        paths = write_wrappers(Path(args.out), default_specs())
        print(json.dumps({"written": [str(path) for path in paths]}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
