#!/usr/bin/env python3
"""Generate command wrappers for mattpocock/skills + Memanto.

This does not install or execute mattpocock/skills. It writes small Claude
command files that document the lifecycle around selected source skills.
"""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_SKILLS = {
    "grill-with-docs": {
        "source": "/grill-with-docs",
        "purpose": "stress-test a plan while preserving resolved terms and ADR-worthy decisions",
        "paths": "CONTEXT.md docs/adr",
    },
    "tdd": {
        "source": "/tdd",
        "purpose": "implement a vertical slice while preserving prior architectural constraints",
        "paths": "src tests",
    },
    "handoff": {
        "source": "/handoff",
        "purpose": "summarize work while carrying forward durable decisions for the next session",
        "paths": "CONTEXT.md docs/adr .",
    },
}


TEMPLATE = """---
name: {name}-memory
description: Run {source} with Memanto cross-skill memory recall and writeback.
argument-hint: "Task summary and relevant files"
---

Before invoking `{source}`, recall relevant engineering memory:

```bash
python examples/claudecode-skills-memanto/skill_memory.py before \\
  --skill {name} \\
  --task "$ARGUMENTS" \\
  --paths {paths}
```

Read `.memanto-skill-memory/injected-context.md` and apply it as prior
engineering context. Treat memory as guidance, not proof; current repository
state wins if it contradicts memory.

Then run `{source}` for this purpose: {purpose}.

After the source skill completes, save a short transcript to
`.memanto-skill-memory/session.md` containing only durable outcomes:

- decisions,
- preferences and project conventions,
- must/never constraints,
- codebase quirks,
- follow-up tasks.

Store the transcript:

```bash
python examples/claudecode-skills-memanto/skill_memory.py after \\
  --skill {name} \\
  --task "$ARGUMENTS" \\
  --paths {paths} \\
  --transcript .memanto-skill-memory/session.md
```
"""


def write_wrappers(output: Path, skills: dict[str, dict[str, str]]) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, config in skills.items():
        path = output / f"{name}-memory.md"
        path.write_text(
            TEMPLATE.format(
                name=name,
                source=config["source"],
                purpose=config["purpose"],
                paths=config["paths"],
            ),
            encoding="utf-8",
        )
        written.append(path)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=".claude/commands",
        help="Directory to write generated command wrappers.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    written = write_wrappers(Path(args.output), DEFAULT_SKILLS)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
