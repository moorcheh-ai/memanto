#!/usr/bin/env python3
"""
Migrate a Hindsight memory bank into Memanto.

Requires:
    HINDSIGHT_API_KEY env var
    HINDSIGHT_BASE_URL env var (optional, defaults to Hindsight cloud)

Run:
    python scripts/migrate_hindsight.py [--dry-run] [--agent <id>]
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
    parser = argparse.ArgumentParser(description="Migrate Hindsight memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--base-url", default=None, help="Hindsight base URL (overrides HINDSIGHT_BASE_URL)")
    parser.add_argument("--bank-id", default=None, help="Specific bank ID to migrate (default: all banks)")
    parser.add_argument("--file", default=None, help="Pre-exported hindsight_export.json (skips live API call)")
    args = parser.parse_args()

    from _shared import print_summary, require_agent
    from exporters.hindsight_export import run_hindsight_export
    from runner import run_migration

    if args.file:
        import json
        export = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        api_key = os.environ.get("HINDSIGHT_API_KEY", "")
        if not api_key:
            print("HINDSIGHT_API_KEY is not set.", file=sys.stderr)
            return 1
        base_url = args.base_url or os.environ.get("HINDSIGHT_BASE_URL", "")
        bank_id = args.bank_id or os.environ.get("HINDSIGHT_BANK_ID", "") or None
        kw: dict = {}
        if base_url:
            kw["base_url"] = base_url
        if bank_id:
            kw["bank_id"] = bank_id
        with tempfile.TemporaryDirectory() as tmp:
            print("Fetching Hindsight export...")
            _, export = run_hindsight_export(api_key, Path(tmp), on_progress=lambda m: print(f"  {m}"), **kw)

    if not args.dry_run:
        agent = require_agent(args.agent, "migrate_hindsight.py")
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
            provider="hindsight",
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
