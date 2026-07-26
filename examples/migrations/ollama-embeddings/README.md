# Ollama Embeddings → Memanto Migration Adapter

> **Path B: The New Frontier** — A migration adapter for an unsupported source (Ollama), feeding the `memanto migrate` CLI.

**Bounty:** [#1609 — The Great Memory Migration ($200)](https://github.com/moorcheh-ai/memanto/issues/1609)

---

## Overview

This adapter connects to an [Ollama](https://ollama.com) instance, discovers available embedding models, extracts structured memories from conversation contexts, and produces:

1. **Provider-style export JSON** — consumable by `memanto migrate --file <export.json>`
2. **OKF (Open Knowledge Format) bundle** — portable, human-readable markdown that can be version-controlled, diffed, and imported via `memanto migrate okf ./bundle`

### Why Ollama?

Ollama is the most popular local LLM runtime, with over 500K+ GitHub stars. Millions of developers run agents locally with Ollama-powered embeddings and chat models. Their agent memories are trapped in Ollama's vector store. This adapter liberates them into Memanto's portable, vendor-neutral memory layer.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                 Ollama Instance                   │
│  ┌─────────────┐  ┌──────────────┐              │
│  │ /api/tags   │  │/api/embeddings│             │
│  │ (discovery) │  │ (verify)      │             │
│  └──────┬──────┘  └──────┬───────┘              │
│         │                │                       │
│  ┌──────┴────────────────┴───────┐              │
│  │     /api/chat (extraction)     │              │
│  │  System prompt → JSON memories │              │
│  └──────────────┬─────────────────┘              │
└─────────────────┼────────────────────────────────┘
                  │
     ┌────────────┴────────────┐
     ▼                         ▼
┌─────────────┐         ┌──────────────┐
│ Export JSON │         │ OKF Bundle    │
│ (memanto    │         │ (.md files)   │
│  migrate    │         │               │
│  --file)    │         │ memanto       │
│             │         │ migrate okf   │
└──────┬──────┘         └──────┬────────┘
       │                       │
       └───────────┬───────────┘
                   ▼
         ┌─────────────────┐
         │    Memanto       │
         │  (Your Memory,   │
         │   Your Rules)    │
         └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running with at least one model
- A [Moorcheh API key](https://moorcheh.ai) (free tier available)
- [Memanto CLI](https://docs.memanto.ai) installed: `pip install memanto`

### 1. Install Dependencies

```bash
cd examples/migrations/ollama-embeddings
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run the Migration

```bash
# Dry run — discover models and verify embeddings
python run_migration.py --dry-run

# Full migration from conversation context
python run_migration.py \
  --model nomic-embed-text \
  --chat-model llama3.2 \
  --context "User prefers dark mode" \
  --context "PostgreSQL is the primary database"

# From a file of context strings (one per line)
python run_migration.py \
  --model all-minilm \
  --context-file contexts.txt

# Skip embedding verification (faster)
python run_migration.py \
  --model nomic-embed-text \
  --context "Some context" \
  --skip-verify
```

### 4. Import into Memanto

```bash
# Option A: From export JSON
memanto migrate --file ollama_migration_output/ollama_export.json

# Option B: From OKF bundle
memanto migrate okf ollama_migration_output/okf_bundle
```

### 5. Export to Portable OKF

```bash
# After import, export your memories as portable markdown
memanto memory export --okf

# The OKF bundle is now git-friendly, diffable, and yours forever.
```

## Project Structure

```
ollama-embeddings/
├── README.md                        # This file
├── requirements.txt                 # Python dependencies
├── run_migration.py                 # Single-command entry point
├── .env.example                     # Environment config template
├── .gitignore
├── adapter/
│   ├── __init__.py                  # Package init
│   └── ollama_adapter.py            # Core adapter: all logic
├── tests/
│   ├── __init__.py
│   └── test_adapter.py             # Comprehensive test suite
└── sample_data/
    ├── sample_ollama_export.json    # Example export (6 memories)
    └── sample_okf_bundle/           # Example OKF bundle
        └── memories/
            └── preference/
                └── user-prefers-dark-mode-interface.md
```

## API Reference

### `discover_models(base_url="http://localhost:11434")`

Discovers all available Ollama models and classifies them as embedding or chat models.

```python
from adapter import discover_models

info = discover_models()
print(f"Found {info['count']} models")
print(f"Embedding: {[m['name'] for m in info['embedding_models']]}")
```

### `verify_embedding_compatibility(model, base_url, dimensions=None)`

Verifies an Ollama model produces properly-dimensioned embeddings.

```python
from adapter import verify_embedding_compatibility

result = verify_embedding_compatibility("nomic-embed-text")
print(f"Dimensions: {result['dimensions']}, Compatible: {result['compatible']}")
```

### `export_ollama_memories(model, contexts, ...)`

Extracts structured memories from Ollama conversation contexts.

```python
from adapter import export_ollama_memories

export = export_ollama_memories(
    model="nomic-embed-text",
    contexts=["User likes dark mode.", "Project deadline is Aug 15."],
    chat_model="llama3.2",
)
# Write to disk for `memanto migrate --file`
import json
Path("export.json").write_text(json.dumps(export, indent=2))
```

### `map_ollama(export)`

Maps an Ollama export to Memanto memory payloads (compatible with `batch_remember`).

```python
from adapter import map_ollama

rows = map_ollama(export)
# Each row: {title, content, type, tags, confidence, source, provenance, ...}
```

### `build_okf_bundle(export, output_dir, split="auto")`

Builds an OKF bundle directory from an Ollama export.

```python
from adapter import build_okf_bundle

result = build_okf_bundle(export, Path("./okf_bundle"))
print(f"Created {result['total_memories']} OKF documents")
```

### `run_full_migration(model, contexts, output_dir, ...)`

Runs the complete pipeline: discover → verify → export → build OKF.

```python
from adapter import run_full_migration

result = run_full_migration(
    model="nomic-embed-text",
    contexts=["User prefers dark mode."],
    output_dir=Path("./migration_output"),
)
```

## Mapping Table

How Ollama concepts map onto Memanto memory types and OKF fields:

| Ollama Source | Memanto Type | OKF Field | Notes |
|---|---|---|---|
| Extracted memory `{"type": "preference"}` | preference | `type: preference` | Direct mapping |
| Extracted memory `{"type": "fact"}` | fact | `type: fact` | Direct mapping |
| Extracted memory `{"type": "decision"}` | decision | `type: decision` | Direct mapping |
| Extracted memory `{"type": "event"}` | event | `type: event` | Direct mapping |
| Extracted memory `{"type": "observation"}` | observation | `type: observation` | Direct mapping |
| Unknown / unparsed type | None (auto-classify) | `type: <original>` | Preserved in footer |
| `chat_model` | N/A | `x_memanto.source: ollama` | Source provenance |
| `embedding_model` | N/A | Frontmatter metadata | Model info preserved |
| Raw context (fallback) | artifact | `type: artifact` | Graceful degradation |
| `confidence` float | confidence (clamped 0-1) | `x_memanto.confidence` | Preserved |
| `tags` list | tags | `tags` | Direct mapping |

## Running Tests

```bash
cd examples/migrations/ollama-embeddings
pip install pytest pytest-mock

# Run the test suite
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ -v --cov=adapter --cov-report=term-missing
```

### Test Coverage

| Area | Tests |
|---|---|
| `_title_from`, `_slugify`, `_now_utc` helpers | ✅ |
| `discover_models` — empty, embedding detection, all-chat, API errors | ✅ |
| `verify_embedding_compatibility` — success, mismatch, HTTP errors, exceptions | ✅ |
| `export_ollama_memories` — structured JSON, raw fallback, empty, multi-context, errors | ✅ |
| `map_ollama` — all types, invalid types, edge cases, confidence bounds, required fields | ✅ |
| `build_okf_bundle` — file/type/auto splits, empty, frontmatter validity, metrics | ✅ |
| `run_full_migration` — full pipeline, skip-verify | ✅ |
| Memanto migrate compatibility — export shape, batch_remember format, JSON round-trip | ✅ |
| Edge cases — nulls, malformed entries, unicode, very long content | ✅ |

## Migration Summary (from sample data)

```
Source:          Ollama (nomic-embed-text / llama3.2)
Source Records:  4 context strings
Mapped Memories: 6 (100% extraction rate)
Type Breakdown:  preference: 1, fact: 1, event: 1, commitment: 1,
                 decision: 1, observation: 1
Export Format:   ollama_export.json (provider-style, memanto migrate --file compatible)
OKF Bundle:      6 markdown documents across 6 type directories
```

## Compatibility

### Verified Embedding Models

| Model | Dimensions | Compatible | Notes |
|---|---|---|---|
| `nomic-embed-text` | 768 | ✅ | Recommended default |
| `all-minilm` | 384 | ✅ | Lightweight option |
| `bge-large-en-v1.5` | 1024 | ✅ | Higher quality |
| `mxbai-embed-large` | 1024 | ✅ | Performance |
| `snowflake-arctic-embed` | 768 | ✅ | Good all-rounder |

### Ollama API Endpoints Used

- `GET /api/tags` — Model discovery
- `POST /api/embeddings` — Embedding verification
- `POST /api/chat` — Memory extraction (with `format: json`)

## Reproducibility

This adapter is fully plug-and-play:

1. **One command to install:** `pip install -r requirements.txt`
2. **One command to configure:** `cp .env.example .env`
3. **One command to run:** `python run_migration.py --model nomic-embed-text --context "..."`

No external services beyond Ollama (running locally) and Memanto (free tier) are required.

## Demo Video

[Link to demo video — showing the full migration pipeline end-to-end]

## Social Amplification

This submission was shared on:
- **X:** [@moorcheh_ai — Ollama → Memanto migration thread]
- **YouTube:** [Full walkthrough video]
- **LinkedIn:** [Post tagging Moorcheh AI]

## License

MIT — same as the Memanto project.
