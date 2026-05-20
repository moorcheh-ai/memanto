#!/usr/bin/env python3
"""Generate memory-aware command wrappers for mattpocock/skills.

Produces Claude Code command files that recall Memanto context before
invoking the source skill and store durable decisions afterward.

Usage::

    python mattpocock_adapter.py --output .claude/commands
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

SKILLS = {
    "grill-with-docs": {
        "command": "/grill-with-docs",
        "purpose": "review code or architecture against supplied docs",
        "paths": "CONTEXT.md docs/adr",
    },
    "tdd": {
        "command": "/tdd",
        "purpose": "drive implementation with tests first",
        "paths": "src tests",
    },
    "handoff": {
        "command": "/handoff",
        "purpose": "summarize current work for another session",
        "paths": "CONTEXT.md docs/adr .",
    },
}

WRAPPER_TEMPLATE = """\
---
name: {name}-memory
description: Run {command} with Memanto cross-skill memory recall and writeback.
argument-hint: "Task summary and relevant files"
---

Before invoking `{command}`, recall relevant engineering memory:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py recall \\
  --skill {name} \\
  --task "$ARGUMENTS" \\
  --file {paths}
```

Read the ``<memanto-engineering-memory>`` block from stdout (or the
``MEMANTO_SKILL_CONTEXT`` environment variable) and apply it as prior
engineering context.  Treat memory as guidance, not proof — current
repository state wins if it contradicts memory.

Then run `{command}` for this purpose: {purpose}.

After the source skill completes, save a short transcript containing only
durable outcomes (decisions, preferences, must/never constraints, codebase
quirks, follow-up tasks) and store it:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py store \\
  --skill {name} \\
  --task "$ARGUMENTS" \\
  --file {paths} \\
  --transcript-file /tmp/skill-transcript.txt
```
"""


@dataclass(frozen=True)
class SkillSpec:
    skill: str
    command: str
    purpose: str
    pre_hook: list[str]
    post_hook: list[str]
    prompt_prefix: str


def build_spec(
    name: str, task: str, files: list[str] | None = None, backend: str = "local"
) -> SkillSpec:
    if name not in SKILLS:
        known = ", ".join(sorted(SKILLS))
        raise ValueError(f"unknown skill {name!r}; expected: {known}")

    files = files or []
    info = SKILLS[name]
    base = ["python", "examples/claudecode-skills-memanto/skill_memory_hook.py"]
    common = ["--backend", backend, "--skill", name, "--task", task]
    for f in files:
        common.extend(["--file", f])

    return SkillSpec(
        skill=name,
        command=info["command"],
        purpose=info["purpose"],
        pre_hook=[*base, "recall", *common],
        post_hook=[*base, "store", *common, "--transcript-file", "$TRANSCRIPT_FILE"],
        prompt_prefix=(
            "Run pre_hook first and prepend its stdout to the skill prompt. "
            "After the skill finishes, write the transcript to $TRANSCRIPT_FILE "
            "and run post_hook."
        ),
    )


def write_wrappers(output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, info in SKILLS.items():
        path = output / f"{name}-memory.md"
        path.write_text(
            WRAPPER_TEMPLATE.format(
                name=name,
                command=info["command"],
                purpose=info["purpose"],
                paths=info["paths"],
            ),
            encoding="utf-8",
        )
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode")

    sub.add_parser("wrappers", help="Generate Claude command wrapper files")
    spec_p = sub.add_parser("spec", help="Print a JSON spec for one skill")
    spec_p.add_argument("skill", choices=sorted(SKILLS))
    spec_p.add_argument("--task", required=True)
    spec_p.add_argument("--file", action="append", default=[])
    spec_p.add_argument("--backend", default="local")

    args = parser.parse_args(argv)

    if args.mode == "wrappers" or args.mode is None:
        for p in write_wrappers(Path(".claude/commands")):
            print(p)
        return 0

    spec = build_spec(args.skill, task=args.task, files=args.file, backend=args.backend)
    print(json.dumps(asdict(spec), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
