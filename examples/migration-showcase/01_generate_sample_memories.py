#!/usr/bin/env python3
"""
Step 1: Generate Sample Memories

Creates sample memory exports in Mem0 and Letta formats, plus an OKF bundle,
to simulate memories trapped in proprietary systems.
"""

from __future__ import annotations

import json
from pathlib import Path

SAMPLE_DIR = Path(__file__).parent / "sample-memories"


def main() -> None:
    print("=" * 70)
    print("  STEP 1: Generating Sample Memories (Simulating Trapped Data)")
    print("=" * 70)

    # --- Mem0 export ---
    mem0_path = SAMPLE_DIR / "mem0_export.json"
    mem0_data = json.loads(mem0_path.read_text())
    categories = sorted({m["category"] for m in mem0_data["memories"]})
    print(f"\n  ✓ Loaded Mem0 export: {mem0_path}")
    print(f"    • {len(mem0_data['memories'])} memories")
    print(f"    • Categories: {categories}")
    print(f"    • Exported at: {mem0_data['exported_at']}")

    # --- Letta export ---
    letta_path = SAMPLE_DIR / "letta_export.json"
    letta_data = json.loads(letta_path.read_text())
    types = sorted({m["metadata"]["type"] for m in letta_data["archival_memories"]})
    print(f"\n  ✓ Loaded Letta export: {letta_path}")
    print(f"    • {len(letta_data['archival_memories'])} archival passages")
    print(f"    • Types: {types}")
    print(f"    • Exported at: {letta_data['exported_at']}")

    # --- OKF bundle ---
    okf_dir = SAMPLE_DIR / "okf_bundle"
    md_files = sorted(okf_dir.rglob("*.md"))
    print(f"\n  ✓ Loaded OKF bundle: {okf_dir}")
    print(f"    • {len(md_files)} markdown files")
    for md in md_files:
        rel = md.relative_to(SAMPLE_DIR)
        with open(md) as f:
            content = f.read()
        # Extract title from frontmatter
        title = "unknown"
        for line in content.split("\n"):
            if line.startswith("title:"):
                title = line.split("title:")[1].strip().strip('"')
                break
        print(f"    • {rel} → \"{title}\"")

    total = (
        len(mem0_data["memories"])
        + len(letta_data["archival_memories"])
        + len(md_files)
    )
    print(f"\n  ─────────────────────────────────────────────────────")
    print(f"  TOTAL: {total} memories ready for migration!")
    print(f"  ─────────────────────────────────────────────────────")
    print(f"\n  Next step: python 02_migrate_to_memanto.py")


if __name__ == "__main__":
    main()
