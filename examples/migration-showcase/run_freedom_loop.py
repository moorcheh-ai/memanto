#!/usr/bin/env python3
"""
The Great Memory Migration: Full Freedom Loop Showcase

Runs the complete migration showcase end-to-end:
  STEP 1: Generate sample memories (simulating trapped data)
  STEP 2: Migrate to Memanto (prove ownership)
  STEP 3: Export as portable OKF (prove portability)
  STEP 4: Reimport OKF (prove round-trip)

Usage:
    python run_freedom_loop.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_step(script: str) -> bool:
    """Run a step script and return True on success."""
    step_path = Path(__file__).parent / script
    if not step_path.exists():
        print(f"\n  ❌ Script not found: {script}")
        return False

    print(f"\n{'#' * 70}")
    print(f"  Running: {script}")
    print(f"{'#' * 70}\n")

    result = subprocess.run(
        [sys.executable, str(step_path)],
        capture_output=False,
    )
    return result.returncode == 0


def main() -> None:
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           THE GREAT MEMORY MIGRATION                          ║
║   Proving the Freedom Loop: IN → OWNED → PORTABLE             ║
╚══════════════════════════════════════════════════════════════╝

This showcase demonstrates how Memanto breaks vendor lock-in
for agentic memories. Follow along as we:

  1. Extract memories from proprietary formats (simulated)
  2. Migrate them into Memanto for full ownership
  3. Export them as portable OKF bundles
  4. Verify the round-trip is lossless
""")

    steps = [
        ("01_generate_sample_memories.py", "Generating sample memories"),
        ("02_migrate_to_memanto.py", "Migrating to Memanto"),
        ("03_export_as_okf.py", "Exporting as portable OKF"),
        ("04_reimport_okf.py", "Reimporting OKF (verifying round-trip)"),
    ]

    for script, description in steps:
        print(f"\n{'─' * 70}")
        print(f"  ▶  {description}")
        print(f"{'─' * 70}")
        success = run_step(script)
        if not success:
            print(f"\n  ❌ Step failed: {script}")
            sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           ✅ FREEDOM LOOP COMPLETE!                           ║
║                                                              ║
║   Memories went from:                                         ║
║     TRAPPED (proprietary format)                              ║
║     → OWNED (in Memanto)                                     ║
║     → PORTABLE (as OKF markdown)                             ║
║     → VERIFIED (round-trip OK)                               ║
║                                                              ║
║   Your agentic memories belong to YOU.                        ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
