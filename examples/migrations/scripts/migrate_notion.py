#!/usr/bin/env python3
"""
Migrate a Notion workspace export into Memanto.

Configure:
    ZIP_PATH = "/path/to/notion_export.zip"   # set this

Export from: Notion settings → Settings & Members → Settings → Export content → HTML or Markdown & CSV

Run:
    python scripts/migrate_notion.py [--dry-run] [--agent <id>]
"""

import argparse
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_MIGRATIONS = _HERE.parent
_REPO_ROOT = _MIGRATIONS.parent.parent
for _p in (_MIGRATIONS, _REPO_ROOT):
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
                    title, tags, body, created_at = _parse_markdown(text, yaml)
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

    from runner import run_migration

    export = _load_notion_zip(zip_path)
    if export is None:
        return 1

    if not export["memories"]:
        print("No markdown files found in the Notion export ZIP.", file=sys.stderr)
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
            provider="notion",
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
