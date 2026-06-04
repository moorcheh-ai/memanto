"""
CLI entrypoint for memanto-skill-hook.

Lets shell scripts and terminal wrappers call the hook directly:

    # Pre-skill: get memory context to inject into prompt
    python -m memanto_skill_hook pre --skill /tdd --file src/auth.ts

    # Post-skill: store distilled learnings
    python -m memanto_skill_hook post --skill /tdd --file src/auth.ts \
        --summary "Used AAA pattern, vitest, mocked auth middleware"
"""

from __future__ import annotations

import argparse
import json
import sys

from memanto_skill_hook.memory import SkillMemory


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memanto-skill-hook",
        description="Cross-skill persistent memory for the mattpocock/skills workflow",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ---- pre (on_skill_start) ----
    pre = sub.add_parser(
        "pre",
        help="Query Memanto before a skill runs (returns context to inject)",
    )
    pre.add_argument("--skill", required=True, help="Skill name, e.g. /tdd")
    pre.add_argument("--file", default="", help="Target file path")
    pre.add_argument("--task", default="", help="Task description")
    pre.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (text for prompt injection, json for scripts)",
    )

    # ---- post (on_skill_complete) ----
    post = sub.add_parser(
        "post",
        help="Store distilled learnings after a skill completes",
    )
    post.add_argument("--skill", required=True, help="Skill name, e.g. /tdd")
    post.add_argument("--file", default="", help="Target file path")
    post.add_argument(
        "--summary", required=True, help="Summary of what the skill produced"
    )
    post.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (text for humans, json for scripts)",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    mem = SkillMemory()

    if args.command == "pre":
        ctx = mem.on_skill_start(
            skill_name=args.skill,
            file_path=args.file,
            task_description=args.task,
        )
        if args.format == "json":
            print(json.dumps({"context": ctx, "has_memories": bool(ctx)}))
        else:
            if ctx:
                print(ctx)
        return 0

    if args.command == "post":
        ok = mem.on_skill_complete(
            skill_name=args.skill,
            summary=args.summary,
            file_path=args.file,
        )
        if args.format == "json":
            print(json.dumps({"stored": ok}))
        else:
            print("ok" if ok else "failed", file=sys.stderr)
        return 0 if ok else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
