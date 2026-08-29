#!/usr/bin/env python3
"""
Migrate a Notion workspace export into Memanto.

Configure:
    ZIP_PATH = "/path/to/notion_export.zip"   # set this

Export from: Notion settings → Settings & Members → Settings → Export content → Markdown & CSV

Run:
    python scripts/migrate_notion.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_HERE, _MIGRATIONS, _REPO_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

# ── configure ────────────────────────────────────────────────────────────────
ZIP_PATH = "/path/to/notion_export.zip"
# ─────────────────────────────────────────────────────────────────────────────


def _load_notion_zip(zip_path: Path) -> dict | None:
    try:
        import yaml
    except ImportError:
        print("pyyaml is required: pip install pyyaml", file=sys.stderr)
        return None

    from _shared import parse_markdown

    memories = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp).resolve()
                for member in zf.infolist():
                    dest = (tmp_path / member.filename).resolve()
                    if not dest.is_relative_to(tmp_path):
                        print("ZIP contains unsafe paths.", file=sys.stderr)
                        return None
                zf.extractall(tmp)
                for md_file in tmp_path.rglob("*.md"):
                    text = md_file.read_text(encoding="utf-8", errors="replace")
                    title, tags, body, created_at = parse_markdown(text, yaml)
                    memories.append({
                        "title": title,
                        "body": body,
                        "filename_stem": md_file.stem,
                        "tags": tags,
                        "created_at": created_at,
                    })
    except zipfile.BadZipFile as exc:
        print(f"Invalid ZIP: {exc}", file=sys.stderr)
        return None

    return {"memories": memories}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Notion export to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--file", default=ZIP_PATH, help="Path to Notion export ZIP")
    args = parser.parse_args()

    zip_path = Path(args.file)
    if not zip_path.is_file():
        print(f"ZIP not found: {zip_path}", file=sys.stderr)
        print("Set ZIP_PATH at the top of this script or pass --file.", file=sys.stderr)
        return 1

    from _shared import print_summary, require_agent
    from runner import run_migration

    export = _load_notion_zip(zip_path)
    if export is None:
        return 1
    if not export["memories"]:
        print("No markdown files found in the Notion export ZIP.", file=sys.stderr)
        return 1

    if not args.dry_run:
        agent = require_agent(args.agent, "migrate_notion.py")
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
            provider="notion",
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
