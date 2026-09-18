#!/usr/bin/env python3
"""
Migrate an Obsidian vault into Memanto.

Configure:
    VAULT_PATH = "/path/to/your/vault"   # set this

Run:
    python scripts/migrate_obsidian.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_HERE, _MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

# ── configure ────────────────────────────────────────────────────────────────
VAULT_PATH = "/path/to/your/obsidian/vault"
# ─────────────────────────────────────────────────────────────────────────────


def _load_vault(vault_path: Path) -> dict | None:
    try:
        import yaml
    except ImportError:
        print("pyyaml is required: pip install pyyaml", file=sys.stderr)
        return None

    from _shared import parse_markdown

    memories = []
    for md_file in vault_path.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        title, tags, body, created_at = parse_markdown(text, yaml)
        memories.append({
            "title": title,
            "body": body,
            "filename_stem": md_file.stem,
            "tags": tags,
            "created_at": created_at,
        })
    return {"memories": memories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Obsidian vault to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--vault", default=VAULT_PATH, help="Path to Obsidian vault directory")
    args = parser.parse_args()

    vault_path = Path(args.vault)
    if not vault_path.is_dir():
        print(f"Vault directory not found: {vault_path}", file=sys.stderr)
        print("Set VAULT_PATH at the top of this script or pass --vault.", file=sys.stderr)
        return 1

    from _shared import print_summary, require_agent
    from runner import run_migration

    export = _load_vault(vault_path)
    if export is None:
        return 1
    if not export["memories"]:
        print("No markdown files found in the vault.", file=sys.stderr)
        return 1

    if not args.dry_run:
        agent = require_agent(args.agent, "migrate_obsidian.py")
        if agent is None:
            return 1
        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            print("MOORCHEH_API_KEY is not set.", file=sys.stderr)
            return 1
        from memanto.cli.client.sdk_client import SdkClient
        client = SdkClient(api_key=api_key)
        client.activate_agent(agent, duration_hours=2)
    else:
        agent = args.agent
        client = None

    try:
        summary, _ = run_migration(
            provider="obsidian",
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
