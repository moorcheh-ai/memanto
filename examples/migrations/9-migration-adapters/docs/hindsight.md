# Hindsight export guide


## How to get your data

Hindsight data is pulled live via the API — no ZIP download needed.

You need a `HINDSIGHT_API_KEY` from your Hindsight dashboard → Settings → API.

## CLI command

```bash
export HINDSIGHT_API_KEY=your_key_here
memanto migrate hindsight --agent <id>
```

For a self-hosted instance, also set `HINDSIGHT_BASE_URL`:

```bash
export HINDSIGHT_BASE_URL=https://your-instance.example.com
memanto migrate hindsight --agent <id>
```

Pass a `--bank-id` to target a specific bank (otherwise all banks are exported):

```bash
memanto migrate hindsight --bank-id my-bank --agent <id>
```

Use a pre-exported JSON to skip the live pull:

```bash
memanto migrate hindsight --file hindsight_export.json --agent <id>
```

Or use the convenience script:

```bash
export HINDSIGHT_API_KEY=your_key_here
python scripts/migrate_hindsight.py [--dry-run] [--agent <id>]
```

## What gets exported

The exporter calls `GET /v1/default/banks` to list banks, then paginates
`GET /v1/default/banks/{bank_id}/memories/list` for each bank.

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `text` | `content` | The memory text; falls back to `content` when `text` is absent |
| `fact_type` | `type` | `observation`→`observation`, `world`→`fact`, `experience`→`event`; others→`None` |
| hardcoded | `source` | `"hindsight"` |
| hardcoded | `provenance` | `"imported"` |
