"""Generate memory-aware wrappers for mattpocock developer skills."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

SKILLS = {
    "grill-with-docs": {
        "command": "/grill-with-docs",
        "purpose": "review implementation choices against source docs",
        "default_files": ("docs", "README.md"),
    },
    "tdd": {
        "command": "/tdd",
        "purpose": "drive code changes from a failing test first",
        "default_files": ("src", "tests"),
    },
    "handoff": {
        "command": "/handoff",
        "purpose": "prepare a compact continuation note for a future session",
        "default_files": ("README.md", "docs"),
    },
}


@dataclass(frozen=True)
class WrapperSpec:
    name: str
    source_command: str
    body: str


def build_specs(backend: str = "local") -> list[WrapperSpec]:
    return [
        WrapperSpec(
            name=f"{name}-memory",
            source_command=info["command"],
            body=_wrapper_body(name, info, backend),
        )
        for name, info in SKILLS.items()
    ]


def write_wrappers(output_dir: Path, backend: str = "local") -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for spec in build_specs(backend=backend):
        path = output_dir / f"{spec.name}.md"
        path.write_text(spec.body, encoding="utf-8")
        paths.append(path)
    return paths


def build_json_spec(
    skill: str, task: str, files: list[str], backend: str
) -> dict[str, object]:
    if skill not in SKILLS:
        raise ValueError(f"unknown skill {skill!r}; expected one of {sorted(SKILLS)}")

    base = ["python3", "examples/claudecode-skills-memanto/skill_memory_bridge.py"]
    common = ["--backend", backend, "--skill", f"/{skill}", "--task", task]
    for file_path in files:
        common.extend(["--file", file_path])

    return {
        "skill": skill,
        "source_command": SKILLS[skill]["command"],
        "pre_hook": [*base, "recall", *common],
        "post_hook": [
            *base,
            "store",
            *common,
            "--transcript-file",
            "$TRANSCRIPT_FILE",
        ],
        "context_env": "MEMANTO_SKILL_CONTEXT",
    }


def _wrapper_body(name: str, info: dict[str, object], backend: str) -> str:
    files = " ".join(
        f"--file {file_path}"
        for file_path in info["default_files"]  # type: ignore[index]
    )
    command = info["command"]
    purpose = info["purpose"]
    return f"""---
name: {name}-memory
description: Run {command} with Memanto cross-skill memory recall and writeback.
argument-hint: "Task summary and relevant files"
---

Run the recall hook before invoking `{command}`:

```bash
python3 examples/claudecode-skills-memanto/skill_memory_bridge.py recall \\
  --backend {backend} \\
  --skill /{name} \\
  --task "$ARGUMENTS" \\
  {files}
```

Prepend the `<memanto-engineering-memory>` block to the skill prompt. The
memory block is guidance only; current repository state and explicit user
instructions win on conflict.

Run the source skill for this purpose: {purpose}.

After the skill finishes, write a short transcript containing durable outcomes
only: decisions, preferences, must/never constraints, codebase quirks,
validation commands, and follow-up tasks. Then run:

```bash
python3 examples/claudecode-skills-memanto/skill_memory_bridge.py store \\
  --backend {backend} \\
  --skill /{name} \\
  --task "$ARGUMENTS" \\
  {files} \\
  --transcript-file /tmp/{name}-skill-transcript.txt
```
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    wrappers = sub.add_parser("wrappers")
    wrappers.add_argument("--output", default=".claude/commands")
    wrappers.add_argument("--backend", choices=("local", "sdk", "cli"), default="local")

    spec = sub.add_parser("spec")
    spec.add_argument("skill", choices=sorted(SKILLS))
    spec.add_argument("--task", required=True)
    spec.add_argument("--file", action="append", default=[])
    spec.add_argument("--backend", choices=("local", "sdk", "cli"), default="local")

    args = parser.parse_args(argv)
    if args.command == "wrappers":
        for path in write_wrappers(Path(args.output), backend=args.backend):
            print(path)
        return 0

    print(
        json.dumps(
            build_json_spec(args.skill, args.task, args.file, args.backend), indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
