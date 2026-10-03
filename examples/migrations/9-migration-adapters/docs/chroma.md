# Chroma export guide

## How to get your data

No export file needed — the CLI connects live to a running ChromaDB instance.

Requires `chromadb` installed:

```bash
pip install chromadb
```

## CLI command

```bash
export CHROMA_COLLECTION=my-collection
memanto migrate chroma --collection my-collection --agent <id>
```

Override host and port if ChromaDB isn't on localhost:8000:

```bash
memanto migrate chroma \
  --collection my-collection \
  --host chroma.internal \
  --port 8000 \
  --agent <id>
```

Dry-run:

```bash
memanto migrate chroma --collection my-collection --dry-run
```

Or use the convenience script:

```bash
export CHROMA_COLLECTION=my-collection
python scripts/migrate_chroma.py [--dry-run] [--agent <id>]
```

## What gets fetched

The CLI calls `collection.get(include=["documents", "metadatas"])` and
normalizes the response into the standard export shape before passing to the mapper.

If `chromadb` is not installed, the command exits with a `pip install chromadb` hint.

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `document` | `content` | The embedded document text |
| `id` | `source_ref` | ChromaDB document ID |
| `metadata.source` | footer in `content` | Appears in `[Supporting data]` block, not as `source` |
| hardcoded | `source` | `"chroma"` |
| hardcoded | `provenance` | `"imported"` |
| hardcoded | `type` | `None` (auto-classified) |
