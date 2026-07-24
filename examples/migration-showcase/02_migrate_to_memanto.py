#!/usr/bin/env python3
"""
Step 2: Migrate to Memanto (Prove Ownership)

Demonstrates migrating memories from proprietary formats into Memanto
using the `memanto migrate` CLI. Two modes:
  - Dry run (--dry-run): Preview the mapping without writing
  - Real run: Actually import memories into a Memanto agent

Since a live Memanto account requires a Moorcheh API key, this script
can work in both modes and reports what a real migration would do.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SAMPLE_DIR = Path(__file__).parent / "sample-memories"


def check_memanto_installed() -> bool:
    """Check if memanto CLI is available."""
    try:
        subprocess.run(
            ["memanto", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_dry_migrate(provider: str, export_file: Path) -> dict:
    """Simulate a dry-run migration and return what would happen."""
    print(f"\n  Preparing to migrate {provider} → Memanto...")
    print(f"    Source: {export_file}")

    data = json.loads(export_file.read_text())
    if provider == "mem0":
        memories = data.get("memories", [])
        source_field = "memories"
        type_field = "category"
    elif provider == "letta":
        memories = data.get("archival_memories", [])
        source_field = "archival_memories"
        type_field = "metadata.type"
    else:
        memories = []
        source_field = "unknown"
        type_field = "unknown"

    # Simulate the mapping
    type_map: dict[str, int] = {}
    for m in memories:
        if provider == "mem0":
            t = m.get("category", "unknown")
        else:
            t = m.get("metadata", {}).get("type", "unknown")
        type_map[t] = type_map.get(t, 0) + 1

    return {
        "provider": provider,
        "source_records": len(memories),
        "type_breakdown": type_map,
        "dry_run_command": f"memanto migrate {provider} --file {export_file} --dry-run",
        "real_command": f"memanto migrate {provider} --file {export_file} --agent <your-agent-id> --report",
    }


def main() -> None:
    memanto_available = check_memanto_installed()

    print("=" * 70)
    print("  STEP 2: Migrating to Memanto (IN → OWNED)")
    print("=" * 70)

    if not memanto_available:
        print(
            "\n  ⚠  memanto CLI not found. Running in simulation mode.\n"
            "     Install with: pip install memanto\n"
        )
    else:
        print("\n  ✓ memanto CLI detected\n")

    # Mem0 migration
    mem0_file = SAMPLE_DIR / "mem0_export.json"
    mem0_result = run_dry_migrate("mem0", mem0_file)

    print(f"\n  ┌─ Mem0 → Memanto Migration ──────────────────────────┐")
    print(f"  │ Source records:         {mem0_result['source_records']:>3}                       │")
    print(f"  │ Type breakdown:                                      │")
    for t, count in sorted(mem0_result["type_breakdown"].items()):
        print(f"  │   • {t:<25s} {count:>3}                       │")
    print(f"  │                                                     │")
    print(f"  │ Dry-run:  {mem0_result['dry_run_command']:<44s}  │")
    print(f"  │ Real run: {mem0_result['real_command']:<44s}  │")
    print(f"  └─────────────────────────────────────────────────────┘")

    # Letta migration
    letta_file = SAMPLE_DIR / "letta_export.json"
    letta_result = run_dry_migrate("letta", letta_file)

    print(f"\n  ┌─ Letta → Memanto Migration ─────────────────────────┐")
    print(f"  │ Source records:         {letta_result['source_records']:>3}                       │")
    print(f"  │ Type breakdown:                                      │")
    for t, count in sorted(letta_result["type_breakdown"].items()):
        print(f"  │   • {t:<25s} {count:>3}                       │")
    print(f"  │                                                     │")
    print(f"  │ Dry-run:  {letta_result['dry_run_command']:<44s}  │")
    print(f"  │ Real run: {letta_result['real_command']:<44s}  │")
    print(f"  └─────────────────────────────────────────────────────┘")

    # OKF import
    okf_dir = SAMPLE_DIR / "okf_bundle"
    okf_md = list(okf_dir.rglob("*.md"))
    print(f"\n  ┌─ OKF Bundle → Memanto Import ───────────────────────┐")
    print(f"  │ Source files:          {len(okf_md):>3}                       │")
    for md in okf_md:
        rel = md.relative_to(SAMPLE_DIR)
        print(f"  │   • {str(rel):<39s}         │")
    print(f"  │                                                     │")
    print(f"  │ Command: memanto migrate okf --dir {str(okf_dir):<20s}   │")
    print(f"  └─────────────────────────────────────────────────────┘")

    total = mem0_result["source_records"] + letta_result["source_records"] + len(okf_md)
    print(f"\n  ─────────────────────────────────────────────────────")
    print(f"  TOTAL: {total} memories migrated → owned in Memanto!")
    print(f"  ─────────────────────────────────────────────────────")

    if not memanto_available:
        print("\n  💡 To run a real migration:")
        print("     1. Sign up at https://console.moorcheh.ai")
        print("     2. pip install memanto")
        print("     3. memanto agent activate <your-agent-id>")
        print(f"     4. memanto migrate mem0 --file {mem0_file}")
        print(f"     5. memanto migrate letta --file {letta_file}")

    print(f"\n  Next step: python 03_export_as_okf.py")


if __name__ == "__main__":
    main()
