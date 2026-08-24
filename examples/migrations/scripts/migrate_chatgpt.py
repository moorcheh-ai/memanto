#!/usr/bin/env python3
"""
Migrate a ChatGPT conversation export into Memanto.

Configure:
    ZIP_PATH = "/path/to/chatgpt_export.zip"   # set this

Run:
    python scripts/migrate_chatgpt.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

# ── configure ────────────────────────────────────────────────────────────────
ZIP_PATH = str(_MIGRATIONS / "sample_data" / "chatgpt_export.zip")
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate ChatGPT export to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--file", default=ZIP_PATH, help="Path to ChatGPT export ZIP")
    args = parser.parse_args()

    zip_path = Path(args.file)
    if not zip_path.exists():
        print(f"ZIP not found: {zip_path}", file=sys.stderr)
        print("Set ZIP_PATH at the top of this script or pass --file.", file=sys.stderr)
        return 1

    from _load_zip import load_conversation_zip
    from runner import run_migration

    export = load_conversation_zip(zip_path, "chatgpt")
    if export is None:
        return 1

    if not args.dry_run:
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            print("MOORCHEH_API_KEY is not set.", file=sys.stderr)
            return 1
        from memanto.cli.client.sdk_client import SdkClient
        client = SdkClient(api_key=api_key)
        client.activate_agent(args.agent, duration_hours=2)
    else:
        client = None

    try:
        summary, _ = run_migration(
            provider="chatgpt",
            export=export,
            client=client,
            agent_id=args.agent or "",
            dry_run=args.dry_run,
            on_progress=lambda msg: print(f"  {msg}"),
        )
    finally:
        if client is not None:
            client.deactivate_agent(args.agent)

    _print_summary(summary, args.dry_run)
    return 0


def _print_summary(summary, dry_run: bool) -> None:
    mode = "Dry run" if dry_run else "Migration"
    print(f"\n{mode} complete")
    print(f"  Source records : {summary.source_count}")
    print(f"  Mapped memories: {summary.mapped_count}  (skipped {summary.skipped})")
    types = ", ".join(f"{k}: {v}" for k, v in summary.type_counts.items()) or "auto"
    print(f"  Type breakdown : {types}")
    if not dry_run:
        print(f"  Imported       : {summary.imported}  Failed: {summary.failed}")


if __name__ == "__main__":
    sys.exit(main())
