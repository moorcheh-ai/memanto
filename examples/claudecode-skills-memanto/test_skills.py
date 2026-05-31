#!/usr/bin/env python3
"""
Verification Script for Memanto Skills Companion

Simulates a real-world multi-session developer workflow:
1. Session 1: The developer aligns on a database design and stores it to Memanto.
2. Session 2: The developer starts coding a model. The companion dynamically 
   recalls the design and injects it as context, avoiding repeat prompt instructions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.resolve()
SKILLS_SCRIPT = BASE_DIR / "memanto_skills.py"
OUTPUT_FILE = BASE_DIR / "test_output_memory.md"
AGENT_ID = "test-skills-agent-mch"


def main() -> None:
    print("=" * 70)
    print("🎯 Simulating Cross-Session Persistent Memory in Claude Code")
    print("=" * 70)

    # 1. Verify environment
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY is not set.")
        print("Please export it before running: export MOORCHEH_API_KEY='mch_...'")
        sys.exit(1)

    # Make sure target output file is clean
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    # 2. Simulate Session 1 (Design Phase complete)
    # The developer finishes a design task and saves architectural decisions to Memanto
    print("\n[Step 1] Session 1: Design Phase completed.")
    print("Storing architectural decision in Memanto...")
    
    summary_text = (
        "We decided to use PostgreSQL for our database and SQLAlchemy as the ORM. "
        "The developer strongly prefers using asynchronous database queries "
        "via SQLAlchemy's AsyncSession to ensure high concurrency and non-blocking I/O. "
        "Do NOT write synchronous database queries."
    )
    
    cmd_session1 = [
        sys.executable,
        str(SKILLS_SCRIPT),
        "end",
        "--task", "Setup database schema and choosing ORM",
        "--summary", summary_text,
        "--tags", "db,orm,preference,postgres",
        "--agent-id", AGENT_ID
    ]
    
    try:
        subprocess.run(cmd_session1, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[-] Session 1 failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "-" * 50)

    # 3. Simulate Session 2 (Coding Phase starts)
    # The developer opens a fresh terminal, starts a coding task, and queries Memanto
    print("[Step 2] Session 2: Fresh Coding Session starts.")
    print("Querying Memanto for relevant context and injecting into the workspace...")

    cmd_session2 = [
        sys.executable,
        str(SKILLS_SCRIPT),
        "start",
        "--task", "Implement user model and postgres database connections",
        "--file", "src/models/user.py",
        "--agent-id", AGENT_ID,
        "--out-file", str(OUTPUT_FILE)
    ]

    try:
        subprocess.run(cmd_session2, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[-] Session 2 failed: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "-" * 50)

    # 4. Verify Output
    print("[Step 3] Verifying injected workspace context...")
    if not OUTPUT_FILE.exists():
        print("[-] Error: Injected memory file was not created!", file=sys.stderr)
        sys.exit(1)

    content = OUTPUT_FILE.read_text(encoding="utf-8")
    print(f"\n[+] Injected Context File Contents ({OUTPUT_FILE.name}):")
    print("=" * 60)
    print(content)
    print("=" * 60)

    # Check for crucial keywords
    if "PostgreSQL" in content and "SQLAlchemy" in content and "AsyncSession" in content:
        print("\n🎉 SUCCESS! Memanto successfully recalled and injected the architectural")
        print("    decisions across separate skill executions with zero repeat instructions!")
    else:
        print("\n[-] Validation failed: Injected context did not contain the expected memory.", file=sys.stderr)
        sys.exit(1)

    # Clean up output file after validation
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()


if __name__ == "__main__":
    main()
