#!/usr/bin/env python3
"""
Dump a LangGraph store and migrate it into Memanto in one step.

Uses an InMemoryStore seeded with demo data when LANGGRAPH_POSTGRES_URI is
absent. Set LANGGRAPH_POSTGRES_URI to connect to a real Postgres-backed store.

Run:
    python scripts/migrate_langgraph.py [--dry-run] [--agent <id>]
"""

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump LangGraph store and migrate to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--file", default=None, help="Pre-dumped langgraph JSON (skips live dump)")
    args = parser.parse_args()

    from runner import run_migration

    if args.file:
        import json
        export = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        import json
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name
        try:
            from dump_langgraph import main as dump_main
            asyncio.run(_run_dump(tmp_path))
            export = json.loads(Path(tmp_path).read_text(encoding="utf-8"))
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

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
            provider="langgraph",
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


async def _run_dump(output: str) -> None:
    import json
    import sys as _sys
    # Import dump_langgraph's internals directly to avoid subprocess
    from dump_langgraph import _get_store, _dump, _seed_demo

    store, postgres = _get_store()
    if not postgres:
        print("No LANGGRAPH_POSTGRES_URI set — using InMemoryStore with demo data.", file=_sys.stderr)
        await _seed_demo(store)
        items = await _dump(store, postgres)
    else:
        async with store as s:
            try:
                await s.setup()
            except Exception as exc:
                print(f"Failed to set up Postgres store: {exc}", file=_sys.stderr)
                raise SystemExit(1)
            items = await _dump(s, postgres)

    with open(output, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Dumped {len(items)} items from LangGraph store")


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
