#!/usr/bin/env python3
"""
Step 3: Export as OKF (Prove Portability)

Demonstrates exporting Memanto memories as an OKF bundle — vendor-neutral,
git-friendly, human-readable markdown with YAML frontmatter.

This is the critical step that proves your memories are truly portable
and not locked into any proprietary format.

Uses PyYAML for standards-compliant YAML serialization that preserves
boolean types and other scalar values through round-trips.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SAMPLE_DIR = Path(__file__).parent / "sample-memories"
OUTPUT_DIR = Path(__file__).parent / "output"
OKF_EXPORT_DIR = OUTPUT_DIR / "okf-export"


def check_memanto_installed() -> bool:
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


def slugify(text: str) -> str:
    """Convert arbitrary text to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:50]


def generate_okf_export(
    memories: list[dict],
    output_dir: Path,
    source_label: str,
) -> list[Path]:
    """Generate OKF-style markdown files from memory data.

    Each file gets a unique, source-qualified filename to prevent collisions
    when multiple providers are exported into the same bundle.
    """
    memories_dir = output_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    created_files = []

    for i, mem in enumerate(memories, 1):
        text = mem.get("text") or mem.get("content") or mem.get("body", "")
        title_text = text[:60] + ("..." if len(text) > 60 else "")

        # Determine type from category/metadata
        mem_type = mem.get("category") or mem.get("metadata", {}).get("type") or "memory"
        confidence = mem.get("metadata", {}).get("confidence", 0.8)
        source = mem.get("metadata", {}).get("source", "unknown")
        created = mem.get("created_at") or mem.get("metadata", {}).get("created_at", "")
        mem_id = mem.get("id") or f"migrated-{i}"

        # Source-qualified slug ensures uniqueness across providers
        slug = slugify(f"{source_label}-{mem_type}-{i:03d}")
        filepath = memories_dir / f"{slug}.md"

        # Preserve ALL unmapped source record-level fields in extra.
        # Only exclude fields already mapped to standard frontmatter keys
        # or dedicated x_memanto keys.
        excluded_meta_keys = {"confidence", "source", "created_at"}
        extra_meta = {
            k: v for k, v in mem.get("metadata", {}).items()
            if k not in excluded_meta_keys
        }
        # Include root-level fields that aren't mapped to standard frontmatter
        for root_key in ("updated_at", "expires_at", "ttl_seconds", "source_ref"):
            if root_key in mem:
                extra_meta[root_key] = mem[root_key]

        frontmatter = {
            "type": mem_type,
            "title": title_text,
            "tags": [mem_type, "migrated", source_label],
            "timestamp": created,
            "x_memanto": {
                "source": source_label,
                "original_id": mem_id,
                "confidence": confidence,
                "extra": extra_meta if extra_meta else None,
            },
        }

        # Use the migration source timestamp instead of wall-clock time
        export_timestamp = created if created else "2026-01-01T00:00:00Z"

        # Build the markdown using PyYAML for standards-compliant output
        # that preserves boolean and scalar types
        lines = ["---"]
        lines.append(yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip())
        lines.append("---")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append(f"> *Migrated from {source_label} on {export_timestamp}*")
        lines.append(f"> *Original ID: {mem_id}*")

        filepath.write_text("\n".join(lines))
        created_files.append(filepath)

    return created_files


def main() -> None:
    memanto_available = check_memanto_installed()

    print("=" * 70)
    print("  STEP 3: Exporting as Portable OKF (OWNED → PORTABLE)")
    print("=" * 70)

    # Clean and create output directory
    if OKF_EXPORT_DIR.exists():
        shutil.rmtree(OKF_EXPORT_DIR)
    OKF_EXPORT_DIR.mkdir(parents=True)

    # Load sample data and generate OKF export
    sources = []

    # Mem0
    mem0_file = SAMPLE_DIR / "mem0_export.json"
    mem0_data = json.loads(mem0_file.read_text())
    mem0_files = generate_okf_export(
        mem0_data["memories"], OKF_EXPORT_DIR, "mem0"
    )
    sources.append(("Mem0", len(mem0_data["memories"]), mem0_files))

    # Letta
    letta_file = SAMPLE_DIR / "letta_export.json"
    letta_data = json.loads(letta_file.read_text())
    letta_files = generate_okf_export(
        letta_data["archival_memories"], OKF_EXPORT_DIR, "letta"
    )
    sources.append(("Letta", len(letta_data["archival_memories"]), letta_files))

    print(f"\n  Generated OKF bundle at: {OKF_EXPORT_DIR}")
    print(f"  ─────────────────────────────────────────────────────")

    for label, count, files in sources:
        print(f"\n  ┌─ {label} ({count} memories) ─────────────────────────┐")
        for f in files:
            rel = f.relative_to(Path(__file__).parent)
            print(f"  │   • {str(rel):<52s}  │")
        print(f"  └────────────────────────────────────────────────────┘")

    total_files = sum(len(files) for _, _, files in sources)
    print(f"\n  ─────────────────────────────────────────────────────")
    print(f"  TOTAL: {total_files} OKF markdown files exported!")
    print(f"  ─────────────────────────────────────────────────────")

    # Show a sample OKF document
    sample_file = mem0_files[0] if mem0_files else letta_files[0]
    print(f"\n  📄 Sample OKF document: {sample_file.relative_to(Path(__file__).parent)}")
    print(f"  {'─' * 70}")
    print(sample_file.read_text()[:500])
    print(f"  {'─' * 70}")

    # If memanto CLI is available, show the real export command
    if memanto_available:
        print(f"\n  💡 Real memanto export command:")
        print(f"     memanto memory export --okf --output {OKF_EXPORT_DIR}")
    else:
        print(f"\n  💡 To export your own Memanto memories as OKF:")
        print("     1. Install memanto: pip install memanto")
        print("     2. Activate your agent: memanto agent activate <id>")
        print("     3. Export: memanto memory export --okf --output ./my-memories")

    print(f"\n  💡 The OKF bundle is now git-friendly:")
    print(f"     cd {OKF_EXPORT_DIR.relative_to(Path(__file__).parent)}")
    print(f"     git init && git add . && git commit -m 'My portable memories'")

    print(f"\n  ✅ Memories are now PORTABLE — no vendor lock-in!")
    print(f"  \n  The freedom loop is complete: IN → OWNED → PORTABLE")
    print(f"\n  Next step: python 04_reimport_okf.py")


if __name__ == "__main__":
    main()
