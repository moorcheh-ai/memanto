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
import subprocess
import sys


def main() -> int:
    """
    Run the Hindsight-to-Memanto migration command using command-line and environment settings.
    
    Returns:
    	int: The migration command's exit code, or `1` when the Hindsight API key is missing.
    """
    parser = argparse.ArgumentParser(description="Migrate Hindsight memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--base-url", default=None, help="Hindsight base URL (overrides HINDSIGHT_BASE_URL env)")
    parser.add_argument("--bank-id", default=None, help="Hindsight bank ID (overrides HINDSIGHT_BANK_ID env)")
    args = parser.parse_args()

    api_key = os.environ.get("HINDSIGHT_API_KEY", "")
    if not api_key:
        print("HINDSIGHT_API_KEY is not set.", file=sys.stderr)
        return 1

    cmd = ["memanto", "migrate", "hindsight"]

    base_url = args.base_url or os.environ.get("HINDSIGHT_BASE_URL", "")
    if base_url:
        cmd += ["--base-url", base_url]

    bank_id = args.bank_id or os.environ.get("HINDSIGHT_BANK_ID", "")
    if bank_id:
        cmd += ["--bank-id", bank_id]

    if args.dry_run:
        cmd.append("--dry-run")
    if args.agent:
        cmd += ["--agent", args.agent]

    env = {**os.environ, "HINDSIGHT_API_KEY": api_key}
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
