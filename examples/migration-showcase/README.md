# Migration Showcase: The Great Memory Migration

**Proving the Freedom Loop: IN → OWNED → PORTABLE**

This showcase demonstrates how to break free from proprietary agentic memory using Memanto's migration toolchain and the Open Knowledge Format (OKF). It proves you can take memories trapped in any tool, migrate them into Memanto for ownership, and export them as portable OKF bundles.

## The Freedom Loop

```
┌─────────────────────────────────────────────────────────────┐
│                      THE FREEDOM LOOP                        │
│                                                              │
│   [TRAPPED MEMORIES]     →     [OWNED IN MEMANTO]            │
│   (Mem0 / Letta /       →      Full control, queryable,     │
│    Supermemory / OKF)   →      typed semantic memory         │
│                                                              │
│        ↑                                      ↓              │
│                                                              │
│   [PORTABLE OKF]       ←      [EXPORT TO OKF]                │
│   Git-friendly,         ←      Vendor-neutral Markdown       │
│   human-readable        ←      with YAML frontmatter         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- Memanto installed (`pip install memanto`)

## Quick Start

```bash
# Run the full migration showcase
python run_freedom_loop.py

# Or run individual steps:
python 01_generate_sample_memories.py   # Create sample memories (simulates another tool)
python 02_migrate_to_memanto.py          # Migrate into Memanto (proves ownership)
python 03_export_as_okf.py              # Export to portable OKF (proves portability)
python 04_reimport_okf.py              # Verify OKF reimport works (proves round-trip)
```

## What This Proves

### Step 1: Memories Are Trapped
Sample memories from another tool (Mem0 format) demonstrate the proprietary lock-in. The data exists but you can't easily move it.

### Step 2: Migration → Ownership
`memanto migrate` maps foreign memories onto Memanto's typed schema (facts, observations, decisions, etc.) for full queryability and control.

### Step 3: Export → Portability
`memanto memory export --okf` produces a clean, git-friendly, human-readable OKF bundle — vendor-neutral Markdown with YAML frontmatter.

### Step 4: Reimport → Round-trip Proof
The OKF bundle can be imported into any Memanto instance losslessly, including unmapped fields.

## Sample Data

The `sample-memories/` directory contains pre-generated sample memory exports you can use without a live Mem0/Letta account:

- `mem0_export.json` — 15 sample memories in Mem0 export format
- `letta_export.json` — 12 sample memories in Letta archival passage format
- `okf_bundle/` — A sample OKF bundle for import testing

## Files

```text
examples/migration-showcase/
├── README.md                       # This file
├── requirements.txt                # Dependencies
├── run_freedom_loop.py             # Full automated showcase
├── 01_generate_sample_memories.py  # Step 1: Generate sample data
├── 02_migrate_to_memanto.py        # Step 2: Migrate to Memanto
├── 03_export_as_okf.py             # Step 3: Export as OKF
├── 04_reimport_okf.py              # Step 4: Reimport OKF (round-trip)
├── sample-memories/
│   ├── mem0_export.json            # Sample Mem0 export
│   ├── letta_export.json           # Sample Letta export
│   └── okf_bundle/                 # Sample OKF bundle
```

## Pro Tip: Record Your Demo

```bash
# Use asciinema to record a terminal demo
asciinema rec demo.cast --title "Memanto Migration Showcase"
python run_freedom_loop.py
asciinema play demo.cast
```

## Links

- [Memanto Migrate CLI Docs](https://docs.memanto.ai/cli/migrate/migrate)
- [Open Knowledge Format Spec](https://docs.memanto.ai/integrations/okf)
- [GitHub Issue #1609](https://github.com/moorcheh-ai/memanto/issues/1609)
