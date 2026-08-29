# Mem0 export guide

## Overview

Mem0 data is pulled live via the API — no ZIP download needed. The exporter fetches all memories for a given agent and maps them into Memanto's typed memory format.

## Prerequisites

You need a `MEM0_API_KEY` from the Mem0 dashboard.

1. Go to [app.mem0.ai](https://app.mem0.ai) and sign in (or create a free account).
2. Open [Settings → API Keys](https://app.mem0.ai/dashboard/settings?tab=api-keys).
3. Click **Create API Key**, give it a name, and copy the key.

```bash
export MEM0_API_KEY=your_key_here
```

## Run the migration

```bash
export MEM0_API_KEY=your_key_here
memanto migrate mem0 --agent <id>
```

> **Security warning:** Avoid passing `--api-key` as a command-line argument.
> API keys passed on the command line are visible in shell history (`~/.bash_history`,
> `~/.zsh_history`) and in the system process list (`ps aux`). Use the environment
> variable above or a `.env` file instead.

## Flags

| Flag | Description | Example |
|---|---|---|
| `--dry-run` | Maps records without writing to Memanto | `memanto migrate mem0 --dry-run --agent <id>` |
| `--file <path>` | Reads from a pre-exported JSON file instead of the live API | `memanto migrate mem0 --file mem0_export.json --agent <id>` |

## Field mapping

| Mem0 field | Memanto field | Notes |
|---|---|---|
| `memory` (primary) / `content` (fallback) | `content` | The memory text |
| `categories[0]` | `type` | Mapped via category map |
| `categories` | `tags` | Full category list |
| `created_at` | `created_at` | Parsed from source timestamp |
| hardcoded | `source` | `"mem0"` |
| hardcoded | `provenance` | `"imported"` |

## Convenience script

```bash
python scripts/migrate_mem0.py [--dry-run] [--agent <id>]
```
