# Manzoma Multi-Agent Migration Showcase

This showcase demonstrates a robust, multi-agent migration workflow using data from **Manzoma ERP**, ensuring strict data isolation and `agent_id` preservation across migration batches.

## Overview
- **Objective:** Migrate multi-agent records from offline JSON bundles (OKF format) into Memanto without losing agent context.
- **Key Features:**
  - `agent_id` frontmatter propagation.
  - Multi-agent batching and session activation.
  - Verification of content isolation across different branch-specific memories.

## How to Run
```bash
python3 manzoma_migration_showcase.py
```

## Requirements
- Python 3.10+
- Memanto Core Package installed in editable mode.
