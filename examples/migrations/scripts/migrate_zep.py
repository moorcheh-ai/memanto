#!/usr/bin/env python3
"""
Migrate Zep Cloud graph edge facts into Memanto.

Requires:
    ZEP_API_KEY env var

Run:
    python scripts/migrate_zep.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_HERE, _MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Zep Cloud memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--file", default=None, help="Pre-exported zep_export.json (skips live API call)")
    args = parser.parse_args()

    from _shared import print_summary, require_agent
    from exporters.zep_export import run_zep_export
    from runner import run_migration

    if args.file:
        import json
        export = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        api_key = os.environ.get("ZEP_API_KEY", "")
        if not api_key:
            print("ZEP_API_KEY is not set.", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            print("Fetching Zep export...")
            _, export = run_zep_export(api_key, Path(tmp), on_progress=lambda m: print(f"  {m}"))

    if not args.dry_run:
        agent = require_agent(args.agent, "migrate_zep.py")
        if agent is None:
            return 1
        moorcheh_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not moorcheh_key:
            print("MOORCHEH_API_KEY is not set.", file=sys.stderr)
            return 1
        from memanto.cli.client.sdk_client import SdkClient
        client = SdkClient(api_key=moorcheh_key)
        client.activate_agent(agent, duration_hours=2)
    else:
        agent = args.agent
        client = None

    try:
        summary, _ = run_migration(
            provider="zep",
            export=export,
            client=client,
            agent_id=agent or "",
            dry_run=args.dry_run,
            on_progress=lambda msg: print(f"  {msg}"),
        )
    finally:
        if client is not None:
            client.deactivate_agent(agent)

    print_summary(summary, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
