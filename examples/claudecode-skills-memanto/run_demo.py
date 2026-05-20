"""Run three isolated skill executions that share Memanto memory."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the credential-free Claude Code skills + Memanto demo.",
    )
    parser.add_argument(
        "--memory-file",
        type=Path,
        default=None,
        help="Write demo memories to this JSONL file for review.",
    )
    parser.add_argument(
        "--keep-memory",
        action="store_true",
        help="Keep the temporary JSONL memory file after the demo exits.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configured_file = os.getenv("MEMANTO_SKILLS_MEMORY_FILE")
    cleanup = False
    if args.memory_file:
        demo_file = args.memory_file
    elif configured_file:
        demo_file = Path(configured_file)
    else:
        handle = tempfile.NamedTemporaryFile(prefix="memanto-skills-", suffix=".jsonl")
        demo_file = Path(handle.name)
        handle.close()
        cleanup = not args.keep_memory

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
    if not cleanup:
        print("Inspect the JSONL file to see the durable memories stored by each run.")
    if cleanup:
        demo_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
