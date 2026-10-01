# Letta export guide

## Overview

Letta stores agent memory as archival passages. This migration pulls those passages
live via the Letta API and maps each one to a Memanto memory.

## Prerequisites

You need a `LETTA_API_KEY` from the Letta platform portal.

1. Go to [platform.letta.com](https://platform.letta.com) and sign in.
2. Open [API Keys](https://platform.letta.com/api-keys).
3. Click **Create API Key**, give it a name, and copy the key.

> The original Letta ADE has been deprecated. Keys are now managed at `platform.letta.com`, not the old ADE UI.

```bash
export LETTA_API_KEY=your_key_here
```

## Run the migration

```bash
export LETTA_API_KEY=your_key_here
memanto migrate letta --agent <id>
```

> **Security warning:** Avoid passing `--api-key` as a command-line argument.
> API keys passed on the command line are visible in shell history (`~/.bash_history`,
> `~/.zsh_history`) and in the system process list (`ps aux`). Use the environment
> variable above or a `.env` file instead.

## Flags

| Flag | Description | Example |
|---|---|---|
| `--dry-run` | Maps records without writing to Memanto | `memanto migrate letta --dry-run` |
| `--file <path>` | Reads from a pre-exported JSON file instead of the live API | `memanto migrate letta --file letta_export.json --agent <id>` |

## Field mapping

| Letta field | Memanto field | Notes |
|---|---|---|
| `text` / `content` from `passages[]` | `content` | `text` is primary; `content` is the fallback |
| `created_at` | `created_at` | Parsed from the passage timestamp |
| agent name / id | `tags` | Format: `"agent=<name>"` or `"agent_id=<id>"` |
| hardcoded | `type` | `"observation"` |
| hardcoded | `source` | `"letta"` |
| hardcoded | `provenance` | `"imported"` |

## Convenience script

```bash
python scripts/migrate_letta.py [--dry-run] [--agent <id>]
```
