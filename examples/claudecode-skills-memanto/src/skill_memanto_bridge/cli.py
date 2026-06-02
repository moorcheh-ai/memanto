from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from .bridge import BridgeConfig, MemoryBridge
from .wrappers import DEFAULT_COMMANDS, generate_wrappers


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "pre-run":
        bridge = MemoryBridge(config=BridgeConfig.from_env())
        injection = bridge.pre_run(skill=args.skill, task=args.task, path=args.path)
        if injection:
            print(injection)
        return 0

    if args.command == "post-run":
        bridge = MemoryBridge(config=BridgeConfig.from_env())
        transcript = read_transcript(args.transcript_file)
        saved = bridge.post_run(
            skill=args.skill,
            task=args.task,
            path=args.path,
            transcript=transcript,
        )
        print(f"saved {len(saved)} memory item(s)")
        return 0

    if args.command == "generate-wrappers":
        generated = generate_wrappers(
            output_dir=args.output_dir,
            commands=args.skills or DEFAULT_COMMANDS,
            runner=args.runner,
        )
        for path in generated:
            print(path)
        return 0

    if args.command == "exec-target":
        return exec_target(args.target, args.args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-memanto",
        description="Inject and extract Memanto memories around developer skill runs.",
    )
    subparsers = parser.add_subparsers(dest="command")

    pre = subparsers.add_parser("pre-run", help="Print relevant memory context.")
    pre.add_argument("--skill", required=True)
    pre.add_argument("--task", required=True)
    pre.add_argument("--path", default=os.getcwd())

    post = subparsers.add_parser("post-run", help="Store active memories from a run.")
    post.add_argument("--skill", required=True)
    post.add_argument("--task", required=True)
    post.add_argument("--path", default=os.getcwd())
    post.add_argument("--transcript-file")

    wrappers = subparsers.add_parser(
        "generate-wrappers",
        help="Create shell and PowerShell launchers for skill commands.",
    )
    wrappers.add_argument("--output-dir", required=True)
    wrappers.add_argument(
        "--runner",
        default="python -m skill_memanto_bridge.cli",
        help="Command used inside generated launchers.",
    )
    wrappers.add_argument("skills", nargs="*")

    exec_parser = subparsers.add_parser(
        "exec-target",
        help="Run a target command string plus forwarded wrapper arguments.",
    )
    exec_parser.add_argument("--target", required=True)
    exec_parser.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def read_transcript(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def exec_target(target: str, forwarded_args: list[str]) -> int:
    command = shlex.split(target)
    if not command:
        print("Target command is empty.", file=sys.stderr)
        return 64
    clean_args = list(forwarded_args)
    if clean_args and clean_args[0] == "--":
        clean_args = clean_args[1:]
    process = subprocess.run(command + clean_args, check=False)
    return int(process.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
