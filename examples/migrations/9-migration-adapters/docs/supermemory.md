# Supermemory export guide

## Overview

Supermemory organizes your knowledge as documents, each containing extracted memory entries and document chunks. The migrator maps memory entries directly; when none are present, it falls back to document chunks tagged as `artifact`.

## Prerequisites

You need a `SUPERMEMORY_API_KEY` from the Supermemory Developer Platform.

1. Go to [console.supermemory.ai](https://console.supermemory.ai) and sign in (Google or GitHub).
2. Navigate to **API Keys** in the sidebar.
3. Copy your org API key (format: `sm_orgId_...`).

```bash
export SUPERMEMORY_API_KEY=your_key_here
```

## Run the migration

```bash
export SUPERMEMORY_API_KEY=your_key_here
memanto migrate supermemory --agent <id>
```

> **Security warning:** Avoid passing `--api-key` as a command-line argument.
> API keys passed on the command line are visible in shell history (`~/.bash_history`,
> `~/.zsh_history`) and in the system process list (`ps aux`). Use the environment
> variable above or a `.env` file instead.

## Flags

| Flag | Description | Example |
|---|---|---|
| `--dry-run` | Maps records without writing to Memanto | `memanto migrate supermemory --dry-run` |
| `--file <path>` | Read from a pre-exported JSON file instead of the live API | `memanto migrate supermemory --file supermemory_export.json --agent <id>` |

## Field mapping

| Supermemory field | Memanto field | Notes |
|---|---|---|
| `content` / `memory` / `text` from `memories[]` | `content` | `content` is primary; `memory` and `text` are fallbacks in order |
| `container_tag` | `tags` | Tag from the parent document container |
| `createdAt` | `created_at` | Parsed from the memory entry |
| hardcoded | `source` | `"supermemory"` |
| hardcoded | `provenance` | `"imported"` |

When a document has no entries in `memories[]`, the migrator falls back to document chunks. Each chunk is mapped with `type` set to `"artifact"` and `confidence` set to `0.7`.

## Convenience script

```bash
python scripts/migrate_supermemory.py [--dry-run] [--agent <id>]
```
