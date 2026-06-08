"""
memanto-skills CLI

Entry point registered as `memanto-skills` (see pyproject.toml).

Commands
--------
recall  <skill-name> [--hint TEXT] [--types TYPE,...] [--limit N]
    Pull engineering memories relevant to a skill and print the context
    block. Claude Code can call this inside a skill to inject context.

store   <skill-name> <summary> [--type TYPE] [--confidence F] [--tags T,...]
    Persist a single engineering insight after a skill completes.

store-file <skill-name> <path> [--type TYPE] [--split] [--confidence F]
    Read a text file and persist its content as one or many memories.

profile [--limit N] [--types TYPE,...]
    Dump your full engineering profile (all stored memories).

clear-agent
    Deactivate the Memanto session for the configured agent.

"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .client import MemantoSkillsClient
from .extractor import extract_memories_from_summary


def _make_client() -> MemantoSkillsClient:
    load_dotenv()
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key.strip():
        print(
            "Error: MOORCHEH_API_KEY is not set.\n"
            "Add it to your .env file or export it: export MOORCHEH_API_KEY=...",
            file=sys.stderr,
        )
        sys.exit(1)
    return MemantoSkillsClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_recall(args: argparse.Namespace) -> None:
    """Print a ready-to-inject context block for a skill."""
    client = _make_client()
    try:
        client.setup()
        types = [t.strip() for t in args.types.split(",")] if args.types else None
        profile = client.recall_for_skill(
            skill_name=args.skill,
            task_hint=args.hint or "",
            memory_types=types,
        )
        block = profile.format_context_block(max_memories=args.limit)
        if block:
            print(block)
        else:
            print(f"# No engineering memories found for `/{args.skill}`.")
            print("# Run a few skills and store insights to build your profile.")
    finally:
        client.teardown()


def cmd_store(args: argparse.Namespace) -> None:
    """Store a single engineering insight."""
    client = _make_client()
    try:
        client.setup()
        extra_tags = (
            [t.strip() for t in args.tags.split(",") if t.strip()]
            if args.tags
            else None
        )
        memory_id = client.store_from_skill(
            skill_name=args.skill,
            summary=args.summary,
            memory_type=args.type,
            confidence=args.confidence,
            extra_tags=extra_tags,
        )
        if memory_id:
            print(f"Stored: {memory_id}")
        else:
            print("Warning: memory may not have been stored (check API key / session).", file=sys.stderr)
            sys.exit(1)
    finally:
        client.teardown()


def cmd_store_file(args: argparse.Namespace) -> None:
    """Read a file and store its content as memories."""
    path = args.path
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()

    if not text:
        print("Error: file is empty.", file=sys.stderr)
        sys.exit(1)

    client = _make_client()
    try:
        client.setup()
        extra_tags = (
            [t.strip() for t in args.tags.split(",") if t.strip()]
            if getattr(args, "tags", None)
            else None
        )
        entries = extract_memories_from_summary(
            skill_name=args.skill,
            summary=text,
            split_sentences=args.split,
            confidence=args.confidence,
            extra_tags=extra_tags,
        )
        if args.type:
            for entry in entries:
                entry["memory_type"] = args.type
        ids = client.batch_store_from_skill(skill_name=args.skill, entries=entries)
        stored = [i for i in ids if i]
        print(f"Stored {len(stored)} / {len(entries)} memories.")
        for mid in stored:
            print(f"  {mid}")
    finally:
        client.teardown()


def cmd_profile(args: argparse.Namespace) -> None:
    """Dump the full engineering profile."""
    client = _make_client()
    try:
        client.setup()
        types = [t.strip() for t in args.types.split(",")] if args.types else None
        profile = client.recall_for_skill(
            skill_name="profile",
            task_hint="engineering profile overview all skills preferences decisions",
            memory_types=types,
        )
        # Override recall limit
        client.recall_limit = args.limit
        profile = client.recall_for_skill(
            skill_name="profile",
            task_hint="engineering profile overview all skills preferences decisions",
            memory_types=types,
        )
        if profile.is_empty:
            print("Your engineering profile is empty. Start using skills and storing insights.")
        else:
            print(f"Engineering profile — {profile.count} memories\n")
            print(profile.format_context_block())
    finally:
        client.teardown()


def cmd_clear(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Deactivate the current Memanto session."""
    client = _make_client()
    client._active = True  # force teardown even if setup was skipped
    client.teardown()
    if client._active:
        print(
            f"Error: failed to deactivate session for agent '{client.agent_id}'.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Session deactivated for agent '{client.agent_id}'.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memanto-skills",
        description="Cross-session memory companion for Claude Code skills.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- recall ---
    p_recall = sub.add_parser("recall", help="Inject engineering context before a skill runs.")
    p_recall.add_argument("skill", help="Skill name (e.g. tdd, grill-with-docs)")
    p_recall.add_argument("--hint", default="", help="Task description to enrich the query")
    p_recall.add_argument("--types", default="", help="Comma-separated memory types to filter")
    p_recall.add_argument("--limit", type=int, default=8, help="Max memories to return (default 8)")
    p_recall.set_defaults(func=cmd_recall)

    # --- store ---
    p_store = sub.add_parser("store", help="Persist an insight after a skill completes.")
    p_store.add_argument("skill", help="Skill that produced this insight")
    p_store.add_argument("summary", help="The insight to store")
    p_store.add_argument("--type", default="learning", help="Memory type (default: learning)")
    p_store.add_argument("--confidence", type=float, default=0.85)
    p_store.add_argument("--tags", default="", help="Extra comma-separated tags")
    p_store.set_defaults(func=cmd_store)

    # --- store-file ---
    p_sf = sub.add_parser("store-file", help="Read a file and store its content as memories.")
    p_sf.add_argument("skill", help="Skill name")
    p_sf.add_argument("path", help="Path to the text file")
    p_sf.add_argument("--type", default="learning", help="Memory type override")
    p_sf.add_argument("--split", action="store_true", help="Split into per-sentence memories")
    p_sf.add_argument("--confidence", type=float, default=0.85)
    p_sf.add_argument("--tags", default="", help="Extra comma-separated tags")
    p_sf.set_defaults(func=cmd_store_file)

    # --- profile ---
    p_prof = sub.add_parser("profile", help="Dump your full engineering profile.")
    p_prof.add_argument("--limit", type=int, default=30)
    p_prof.add_argument("--types", default="", help="Filter to specific memory types")
    p_prof.set_defaults(func=cmd_profile)

    # --- clear-agent ---
    p_clear = sub.add_parser("clear-agent", help="Deactivate the Memanto session.")
    p_clear.set_defaults(func=cmd_clear)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
