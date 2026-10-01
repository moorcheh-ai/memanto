# LangGraph export guide


## How to get your data

Run the dump script against your LangGraph store to produce a JSON file:

```bash
python scripts/dump_langgraph.py --output dump.json
```

With a Postgres-backed store:

```bash
export LANGGRAPH_POSTGRES_URI=postgresql://user:pass@host:5432/db
python scripts/dump_langgraph.py --output dump.json
```

Without `LANGGRAPH_POSTGRES_URI`, the script uses an `InMemoryStore` seeded with demo data.

## CLI command

```bash
memanto migrate langgraph --file dump.json --agent <id>
```

Dry-run:

```bash
memanto migrate langgraph --file dump.json --dry-run --report
```

Or use the self-contained script (dumps then migrates in one step):

```bash
python scripts/migrate_langgraph.py [--dry-run] [--agent <id>]
```

## Expected output shape

```json
{
  "items": [
    {
      "namespace": ["user", "alice", "memories"],
      "key": "pref-editor",
      "value": { "content": "Alice uses VSCode with dark mode." },
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `value.content` or `value` (str) | `content` | Dict with `content` key preferred |
| `key` | `source_ref` | Item key |
| `namespace` (joined with `/`) | `tags` | e.g. `["user/alice/memories"]` |
| hardcoded | `source` | `"langgraph"` |
| hardcoded | `provenance` | `"imported"` |
| hardcoded | `type` | `None` (auto-classified) |
