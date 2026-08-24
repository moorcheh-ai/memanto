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
for _p in (_MIGRATIONS, _REPO_ROOT):
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

    memories = []
    for md_file in vault_path.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        title, tags, body, created_at = _parse_markdown(text, yaml)
        memories.append({
            "title": title,
            "body": body,
            "filename_stem": md_file.stem,
            "tags": tags,
            "created_at": created_at,
        })

    return {"memories": memories}


def _parse_markdown(text: str, yaml) -> tuple:
    title = ""
    tags: list = []
    created_at = None
    body = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            rest = text[end + 3:].strip()
            try:
                fm = yaml.safe_load(fm_text) or {}
                title = str(fm.get("title") or fm.get("Title") or "")
                tags = [str(t) for t in (fm.get("tags") or fm.get("Tags") or []) if t]
                created_at = str(fm.get("created") or fm.get("Created") or "")
                if not created_at:
                    created_at = None
            except Exception:
                pass
            body = rest

    return title, tags, body, created_at


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

    from runner import run_migration

    export = _load_vault(vault_path)
    if export is None:
        return 1

    if not export["memories"]:
        print("No markdown files found in the vault.", file=sys.stderr)
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
            provider="obsidian",
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
