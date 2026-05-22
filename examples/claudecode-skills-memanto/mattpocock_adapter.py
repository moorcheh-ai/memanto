"""Generate wrappers that add Memanto memory to mattpocock-style skills."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from skill_memory import SKILL_NAMES

WRAPPER_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

skill_name="{skill_name}"
bridge_dir="{bridge_dir}"
transcript="$(mktemp)"

python "$bridge_dir/skill_memory.py" before \\
  --skill "$skill_name" \\
  --prompt "$*" \\
  --cwd "$PWD"

"{target_command}" "$@" 2>&1 | tee "$transcript"

python "$bridge_dir/skill_memory.py" after \\
  --skill "$skill_name" \\
  --transcript-file "$transcript" \\
  --cwd "$PWD"
"""


def render_wrapper(skill_name: str, target_command: str, bridge_dir: Path) -> str:
    """Return a shell wrapper for one skill command."""

    return WRAPPER_TEMPLATE.format(
        skill_name=skill_name,
        target_command=shlex.quote(target_command),
        bridge_dir=shlex.quote(str(bridge_dir.resolve())),
    )


def install_wrappers(output_dir: Path, *, bridge_dir: Path) -> list[Path]:
    """Create executable wrappers for the supported developer skills."""

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for skill_name in SKILL_NAMES:
        wrapper = output_dir / skill_name.removeprefix("/")
        wrapper.write_text(
            render_wrapper(skill_name, skill_name, bridge_dir),
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        created.append(wrapper)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bridge-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    for path in install_wrappers(args.output_dir, bridge_dir=args.bridge_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
