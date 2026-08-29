#!/usr/bin/env python3
"""
Migrate Mem0 memories into Memanto.

Requires:
    MEM0_API_KEY env var (exits when neither --api-key nor MEM0_API_KEY is provided)

Run:
    python scripts/migrate_mem0.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import subprocess
import sys


def main() -> int:
    """
    Migrate Mem0 memories to Memanto using command-line options.
    
    Returns:
        int: Exit status of the migration command, or 1 if no Mem0 API key is available.
    """
    parser = argparse.ArgumentParser(description="Migrate Mem0 memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    args = parser.parse_args()

    api_key = os.environ.get("MEM0_API_KEY", "")
    if not api_key:
        print("MEM0_API_KEY is not set.", file=sys.stderr)
        return 1

    cmd = ["memanto", "migrate", "mem0"]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.agent:
        cmd += ["--agent", args.agent]

    env = {**os.environ, "MEM0_API_KEY": api_key}
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
