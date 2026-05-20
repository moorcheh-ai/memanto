"""Run three isolated skill executions that share Memanto memory."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge


def main() -> int:
    configured_file = os.getenv("MEMANTO_SKILLS_MEMORY_FILE")
    cleanup = False
    if configured_file:
        demo_file = Path(configured_file)
    else:
        handle = tempfile.NamedTemporaryFile(prefix="memanto-skills-", suffix=".jsonl")
        demo_file = Path(handle.name)
        handle.close()
        cleanup = True

    bridge = SkillMemoryBridge(LocalJsonlBackend(demo_file))
    base = [sys.executable, str(Path(__file__).with_name("demo_skills.py"))]
    runs = [
        ("grill-with-docs", "review architecture docs", [*base, "grill-with-docs"]),
        ("tdd", "write tests for memory bridge", [*base, "tdd"]),
        ("handoff", "summarize implementation constraints", [*base, "handoff"]),
    ]
    for skill, task, command in runs:
        print(f"\n=== /{skill} ===")
        status = bridge.run(skill, command, task=task)
        if status:
            return status

    print(f"\nMemory file: {demo_file}")
    if cleanup:
        demo_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
