"""CLI for Claude Code skill memory hook events."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from .bridge import SkillEvent, SkillMemoryBridge, build_backend_from_env, run_wrapped_command
except ImportError:
    from bridge import SkillEvent, SkillMemoryBridge, build_backend_from_env, run_wrapped_command


def _read_event(path: str | None) -> SkillEvent:
    if path:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
    return SkillEvent.from_payload(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Memanto skill memory bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre = subparsers.add_parser("pre", help="Recall memory before a skill run")
    pre.add_argument("--event", help="Path to event JSON")
    pre.add_argument("--limit", type=int, default=8)
    pre.add_argument("--max-chars", type=int, default=1200)

    post = subparsers.add_parser("post", help="Store memory after a skill run")
    post.add_argument("--event", help="Path to event JSON")

    run = subparsers.add_parser("run", help="Wrap a skill command")
    run.add_argument("--event", help="Path to event JSON")
    run.add_argument("wrapped", nargs=argparse.REMAINDER)

    args = parser.parse_args()

    if args.command == "run":
        event = _read_event(args.event)
        command = args.wrapped[1:] if args.wrapped[:1] == ["--"] else args.wrapped
        if not command:
            parser.error("run requires a command after --")
        return run_wrapped_command(event, command)

    event = _read_event(args.event)
    bridge = SkillMemoryBridge(build_backend_from_env())

    if args.command == "pre":
        context = bridge.before_skill(event, limit=args.limit, max_chars=args.max_chars)
        if context:
            print(context)
        return 0

    stored = bridge.after_skill(event)
    print(json.dumps({"stored": stored}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
