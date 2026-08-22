#!/usr/bin/env python3
"""
Migrate a ChatGPT conversation export into Memanto.

Configure:
    ZIP_PATH = "/path/to/chatgpt_export.zip"   # set this

Run:
    python scripts/migrate_chatgpt.py [--dry-run] [--agent <id>]
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ── configure ────────────────────────────────────────────────────────────────
ZIP_PATH = str(Path(__file__).parent.parent / "sample_data" / "chatgpt_export.zip")
# ─────────────────────────────────────────────────────────────────────────────


def run_conversation_migration(zip_path: str, source: str, dry_run: bool, agent: str | None) -> int:
    cmd = ["memanto", "migrate", "conversations", zip_path, "--source", source]
    if dry_run:
        cmd.append("--dry-run")
    if agent:
        cmd += ["--agent", agent]
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print("memanto not found. Run `pip install -e .` from the repo root.", file=sys.stderr)
        return 1


def main() -> int:
    """
    Run the Memanto migration for the configured ChatGPT export.
    
    Returns:
    	int: The Memanto command's exit code, or 1 if the configured ZIP file does not exist.
    """
    parser = argparse.ArgumentParser(description="Migrate ChatGPT export to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    args = parser.parse_args()

    if not Path(ZIP_PATH).exists():
        print(f"ZIP not found: {ZIP_PATH}", file=sys.stderr)
        print("Set ZIP_PATH at the top of this script to your ChatGPT export zip.", file=sys.stderr)
        return 1

    return run_conversation_migration(ZIP_PATH, "chatgpt", args.dry_run, args.agent)


if __name__ == "__main__":
    sys.exit(main())
