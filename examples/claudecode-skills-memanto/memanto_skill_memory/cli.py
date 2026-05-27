from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from memanto_skill_memory.backends import backend_from_env
from memanto_skill_memory.hook import SkillMemoryBridge
from memanto_skill_memory.mattpocock_adapter import DEFAULT_SKILLS, build_wrapper_script
from memanto_skill_memory.models import SkillEvent


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memanto-skill-memory",
        description="Add Memanto engineering memory to developer skill commands.",
    )
    subparsers = parser.add_subparsers(required=True)

    pre = subparsers.add_parser("pre", help="Recall context before a skill runs")
    _add_event_args(pre, transcript=False)
    pre.add_argument("--limit", type=int, default=5)
    pre.set_defaults(func=_pre)

    post = subparsers.add_parser("post", help="Store memories after a skill runs")
    _add_event_args(post, transcript=True)
    post.set_defaults(func=_post)

    wrap = subparsers.add_parser("wrap", help="Run a command through pre/post hooks")
    _add_event_args(wrap, transcript=False)
    wrap.add_argument("command", nargs=argparse.REMAINDER)
    wrap.set_defaults(func=_wrap)

    install = subparsers.add_parser(
        "install-mattpocock",
        help="Generate wrappers for common mattpocock-style skill commands",
    )
    install.add_argument("--output-dir", default=".memanto-skills/bin")
    install.set_defaults(func=_install_mattpocock)

    return parser


def _add_event_args(parser: argparse.ArgumentParser, transcript: bool) -> None:
    parser.add_argument("--skill", required=True)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--cwd", default=os.getcwd())
    if transcript:
        parser.add_argument(
            "--transcript-file",
            help="Transcript file. Reads stdin when omitted.",
        )


def _bridge(cwd: str) -> SkillMemoryBridge:
    return SkillMemoryBridge(backend=backend_from_env(Path(cwd)))


def _pre(args: argparse.Namespace) -> int:
    event = SkillEvent(
        skill_name=args.skill,
        prompt=args.prompt,
        transcript="",
        cwd=args.cwd,
    )
    context = _bridge(args.cwd).before_skill(event, limit=args.limit)
    if context:
        print(context)
    return 0


def _post(args: argparse.Namespace) -> int:
    transcript = _read_transcript(args.transcript_file)
    event = SkillEvent(
        skill_name=args.skill,
        prompt=args.prompt,
        transcript=transcript,
        cwd=args.cwd,
    )
    stored = _bridge(args.cwd).after_skill(event)
    print(f"stored {len(stored)} memories")
    return 0


def _wrap(args: argparse.Namespace) -> int:
    command = _strip_command_separator(args.command)
    if not command:
        raise SystemExit("wrap requires a command after --")

    prompt = args.prompt or " ".join(command)
    pre_event = SkillEvent(
        skill_name=args.skill,
        prompt=prompt,
        transcript="",
        cwd=args.cwd,
        command=tuple(command),
    )
    bridge = _bridge(args.cwd)
    context = bridge.before_skill(pre_event)

    env = os.environ.copy()
    if context:
        context_path = Path(args.cwd) / ".memanto-skills" / "last_context.md"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(context, encoding="utf-8")
        env["MEMANTO_SKILL_CONTEXT"] = context
        env["MEMANTO_SKILL_CONTEXT_FILE"] = str(context_path)

    completed = subprocess.run(
        command, cwd=args.cwd, env=env, text=True, capture_output=True
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)

    transcript = "\n".join(
        part
        for part in [
            f"$ {' '.join(command)}",
            completed.stdout,
            completed.stderr,
        ]
        if part
    )
    post_event = SkillEvent(
        skill_name=args.skill,
        prompt=prompt,
        transcript=transcript,
        cwd=args.cwd,
        command=tuple(command),
    )
    bridge.after_skill(post_event)
    return completed.returncode


def _install_mattpocock(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for skill_name, command in DEFAULT_SKILLS.items():
        wrapper_name = f"memanto-{skill_name}"
        wrapper_path = output_dir / wrapper_name
        wrapper_path.write_text(
            build_wrapper_script(wrapper_name, skill_name, command),
            encoding="utf-8",
        )
        wrapper_path.chmod(0o755)
        print(wrapper_path)
    return 0


def _read_transcript(transcript_file: str | None) -> str:
    if transcript_file:
        return Path(transcript_file).read_text(encoding="utf-8")
    return sys.stdin.read()


def _strip_command_separator(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


if __name__ == "__main__":
    raise SystemExit(main())
