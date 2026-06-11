"""``memanto-skills`` CLI — manual control over the skill memory layer.

The lifecycle hooks make memory automatic; this CLI is the manual escape hatch
(and what the /memanto-companion skill shells out to):

    memanto-skills recall <skill> [--hint TEXT]   # print injectable context
    memanto-skills store  <skill> "summary..."    # distill + persist
    memanto-skills profile                         # show accumulated profile
    memanto-skills install [--global]              # register lifecycle hooks
    memanto-skills doctor                          # check config + connectivity

Uses only the standard library (argparse) to stay dependency-light.
"""

from __future__ import annotations

import argparse
import sys

from .client import SkillMemory
from .config import ConfigError, SkillsConfig
from .skill_map import known_skills


def main(argv: list[str] | None = None) -> int:
    """Dispatch the ``memanto-skills`` CLI.

    Parses ``argv`` (defaulting to ``sys.argv``), runs the matching subcommand,
    and returns its exit code. Network/API failures are surfaced as a single
    clean error line, not a traceback.
    """
    parser = argparse.ArgumentParser(
        prog="memanto-skills",
        description="Cross-session engineering memory for Claude Code skills.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_recall = sub.add_parser("recall", help="Print injectable context for a skill.")
    p_recall.add_argument("skill", help="Skill name, e.g. tdd, grill-with-docs.")
    p_recall.add_argument("--hint", default=None, help="Current task hint.")

    p_store = sub.add_parser("store", help="Distill a session summary into memory.")
    p_store.add_argument("skill", help="Skill name the summary came from.")
    p_store.add_argument("summary", help="Free-text session summary.")

    sub.add_parser("profile", help="Show the accumulated engineering profile.")
    sub.add_parser("doctor", help="Check configuration and connectivity.")

    p_install = sub.add_parser("install", help="Register Claude Code lifecycle hooks.")
    p_install.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="Install into ~/.claude/settings.json instead of ./.claude/settings.json.",
    )

    p_uninstall = sub.add_parser("uninstall", help="Remove the lifecycle hooks.")
    p_uninstall.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="Uninstall from ~/.claude/settings.json instead of ./.claude/settings.json.",
    )

    args = parser.parse_args(argv)

    if args.command == "install":
        from .installer import install_hooks

        return install_hooks(global_scope=args.global_scope)

    if args.command == "uninstall":
        from .installer import uninstall_hooks

        return uninstall_hooks(global_scope=args.global_scope)

    if args.command == "doctor":
        return _doctor()

    try:
        mem = SkillMemory()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        return _run_memory_command(mem, args)
    except Exception as exc:  # network/API failures — show cleanly, not as a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run_memory_command(mem: SkillMemory, args: argparse.Namespace) -> int:
    if args.command == "recall":
        profile = mem.recall_for_skill(args.skill, task_hint=args.hint)
        block = profile.format_context_block(skill_name=args.skill)
        if block:
            print(block)
        else:
            print("(no relevant memories yet)", file=sys.stderr)
        return 0

    if args.command == "store":
        stored = mem.distill_and_store(args.skill, args.summary)
        print(f"stored {len(stored)} memory(ies) from /{args.skill}")
        for m in stored:
            mtype = m.get("type") or "memory"
            title = m.get("title") or (m.get("content") or "")[:80] or "(no title)"
            print(f"  - [{mtype}] {title}")
        return 0

    if args.command == "profile":
        block = mem.profile_block()
        print(block or "(profile is empty)")
        return 0

    return 1


def _doctor() -> int:
    try:
        cfg = SkillsConfig.from_env()
    except ConfigError as exc:
        print(f"✗ config: {exc}", file=sys.stderr)
        return 2
    print(f"✓ MOORCHEH_API_KEY set (…{cfg.api_key[-4:]})")
    print(f"✓ agent_id: {cfg.agent_id}")
    print(f"✓ recall_limit: {cfg.recall_limit}, min_similarity: {cfg.min_similarity}")
    print(f"✓ curated skill routes: {', '.join(known_skills())} (others use a generic route)")
    try:
        mem = SkillMemory(cfg)
        mem.setup()
        print("✓ connected to Memanto and session active")
    except Exception as exc:
        print(f"✗ connectivity: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
