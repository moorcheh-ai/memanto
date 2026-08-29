#!/usr/bin/env python3
"""
Migrate Letta agent memories into Memanto.

Requires:
    LETTA_API_KEY env var (exits when neither --api-key nor LETTA_API_KEY is provided)

Run:
    python scripts/migrate_letta.py [--dry-run] [--agent <id>]
"""

import argparse
import os
import subprocess
import sys


def main() -> int:
    """
    Run the Letta memory migration through the Memanto CLI.
    
    Returns:
        int: The subprocess exit status, or 1 when no Letta API key is provided.
    """
    parser = argparse.ArgumentParser(description="Migrate Letta memories to Memanto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agent", default=None)
    args = parser.parse_args()

    api_key = os.environ.get("LETTA_API_KEY", "")
    if not api_key:
        print("LETTA_API_KEY is not set.", file=sys.stderr)
        return 1

    cmd = ["memanto", "migrate", "letta"]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.agent:
        cmd += ["--agent", args.agent]

    env = {**os.environ, "LETTA_API_KEY": api_key}
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
