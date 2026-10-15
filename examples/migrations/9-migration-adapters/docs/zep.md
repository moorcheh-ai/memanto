# Zep export guide

## How to get your data

Zep data is pulled live via the API — no ZIP download needed.

You need a `ZEP_API_KEY` from [app.getzep.com](https://app.getzep.com) → Settings → API Keys.

## CLI command

```bash
export ZEP_API_KEY=your_key_here
memanto migrate zep --agent <id>
```

> **Security warning:** Avoid passing `--api-key` as a command-line argument.
> API keys passed on the command line are visible in shell history (`~/.bash_history`,
> `~/.zsh_history`) and in the system process list (`ps aux`). Use the environment
> variable above or a `.env` file instead.

Dry-run (exports data but doesn't write to Memanto):

```bash
memanto migrate zep --dry-run
```

Or use the convenience script:

```bash
export ZEP_API_KEY=your_key_here
python scripts/migrate_zep.py [--dry-run] [--agent <id>]
```

## What gets exported

The exporter paginates `GET /api/v2/users-ordered` to list all users, then calls
`POST /api/v2/graph/edge/user/{user_id}` for each user to retrieve graph edge facts.

Each edge fact becomes one Memanto memory.

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `fact` | `content` | The fact text |
| `valid_at` or `created_at` | `created_at` | `valid_at` checked first; falls back to `created_at` via `_parse_dt` |
| `score` or `relevance` | `confidence` | Clamped to 0–1; defaults to 0.8 when absent |
| hardcoded | `type` | `"fact"` |
| hardcoded | `source` | `"zep"` |
| hardcoded | `provenance` | `"imported"` |
