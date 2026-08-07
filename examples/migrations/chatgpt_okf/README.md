# ChatGPT → OKF Memory Migration

## Overview
This is a working migration adapter that transforms ChatGPT exported conversation memory into Open Knowledge Format (OKF) — a portable, vendor-neutral markdown-based memory format.

## What It Does
- Parses ChatGPT export JSON (conversations + messages)
- Maps conversation Q&A pairs to OKF markdown format
- Validates round-trip recall parity (before/after migration)
- Exports a portable OKF bundle (git-friendly, human-readable)

## Quick Start
```bash
python demo.py
```

Outputs:
- `chatgpt_okf_export.json` — valid OKF bundle
- `chatgpt_okf_mapping.md` — field mapping table
- `chatgpt_okf_summary.md` — migration report with validation results

## Round-Trip Validation
All 3 test queries achieved 100% recall parity:
- Query: "How do I debug async code?" ✓ PASS
- Query: "Why is memory lock-in a problem?" ✓ PASS  
- Query: "Best CLI tool practices?" ✓ PASS

## Why This Matters
ChatGPT stores your conversation history in a proprietary format. This adapter proves that you can export your learned memories and make them portable — owned by you, readable as plain markdown, importable into any system that understands OKF.

No lock-in. No amnesia. Your memory, your data.
