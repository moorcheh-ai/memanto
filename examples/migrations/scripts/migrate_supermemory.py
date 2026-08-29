#!/usr/bin/env python3
"""
Migrate Supermemory memories into Memanto.

Requires:
    SUPERMEMORY_API_KEY env var (exits when neither --api-key nor SUPERMEMORY_API_KEY is provided)

Run:
    python scripts/migrate_supermemory.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import subprocess
import sys


def main() -> int:
    """Run the Supermemory-to-Memanto migration command.
    
    Returns:
        int: The migration command's exit status, or 1 when no Supermemory API
            key is configured.
    """
    parser = argparse.ArgumentParser(description="Migrate Supermemory memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--api-key", default=None, help="Supermemory API key (overrides SUPERMEMORY_API_KEY env)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("SUPERMEMORY_API_KEY", "")
    if not api_key:
        print("SUPERMEMORY_API_KEY is not set. Export it or pass --api-key.", file=sys.stderr)
        return 1

    cmd = ["memanto", "migrate", "supermemory"]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.agent:
        cmd += ["--agent", args.agent]

    env = {**os.environ, "SUPERMEMORY_API_KEY": api_key}
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
