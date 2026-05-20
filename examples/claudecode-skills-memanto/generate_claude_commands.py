"""Generate Claude command wrappers for selected mattpocock skills."""

from __future__ import annotations

import argparse
from pathlib import Path

SKILLS = ("grill-with-docs", "tdd", "handoff")


TEMPLATE = """---
description: Run /{skill} with Memanto cross-skill memory
---

Before executing the skill, recall relevant engineering memories:

```bash
python examples/claudecode-skills-memanto/skill_memory_bridge.py {skill} \\
  --task "$ARGUMENTS" -- <original-{skill}-command> "$ARGUMENTS"
```

Use the printed `MEMANTO_SKILL_CONTEXT` as additional constraints for this run.
After the command exits, the bridge stores durable decisions, conventions,
instructions, and caveats back into Memanto for the next skill.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(".claude/commands"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        path = args.out / f"{skill}-with-memanto.md"
        path.write_text(TEMPLATE.format(skill=skill), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
