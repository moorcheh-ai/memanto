#!/usr/bin/env python3
"""Example wrapper that surrounds a skill command with Memanto memory."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from memanto_skills_hook import (
    SkillRun,
    build_backend,
    build_context_block,
    store_completed_run,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument(
        "--backend",
        choices=("memanto-sdk", "memanto-cli", "local-jsonl"),
        default=os.environ.get("MEMANTO_SKILLS_BACKEND", "memanto-cli"),
    )
    parser.add_argument(
        "--store",
        default=os.environ.get(
            "MEMANTO_SKILLS_STORE",
            ".memanto-skills-preview.jsonl",
        ),
        help="JSONL path used by --backend local-jsonl.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if not args.command:
        parser.error("provide the skill command after --")
    if args.command[0] == "--":
        args.command = args.command[1:]

    backend = build_backend(args.backend, args.store)
    run = SkillRun(skill=args.skill, task=args.task, files=tuple(args.file))
    context = build_context_block(run, backend)
    if context:
        print(context)
        print()

    env = os.environ.copy()
    if context:
        env["MEMANTO_SKILL_CONTEXT"] = context

    completed = subprocess.run(
        args.command,
        capture_output=True,
        text=True,
        env=env,
    )
    transcript = "\n".join(
        part for part in (completed.stdout, completed.stderr) if part.strip()
    )
    print(completed.stdout, end="")
    print(completed.stderr, end="", file=sys.stderr)

    store_completed_run(
        SkillRun(
            skill=args.skill,
            task=args.task,
            files=tuple(args.file),
            transcript=transcript,
        ),
        backend,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
