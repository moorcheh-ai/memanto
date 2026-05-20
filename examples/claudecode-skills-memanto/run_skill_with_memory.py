"""Run a skill command with Memanto memory injection and capture."""

from __future__ import annotations

import argparse
import sys

from skill_memory import SkillMemoryHook, build_memory_store


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wrap a skill command with Memanto memory recall/capture."
    )
    parser.add_argument("--skill", required=True, help="Skill name, e.g. /tdd")
    parser.add_argument("--task", required=True, help="Current skill task")
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        help="Relevant file path. May be repeated.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run after --, e.g. -- python script.py",
    )
    args = parser.parse_args()

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Provide a command after --")

    hook = SkillMemoryHook(build_memory_store())
    context_block = hook.before_skill(args.skill, args.task, args.files)
    if context_block:
        print(context_block)
        print()

    result = hook.run_skill_command(args.skill, command, args.task, args.files)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
