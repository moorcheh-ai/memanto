# Qdrant → Memanto → OKF: The Vector-Store Escape

**Path B — The New Frontier.** The most common production vector store used to
back agent memory (Mem0, LangChain memory, RAG stacks) gets a first-class
escape route: a raw Qdrant collection → Memanto → portable OKF markdown.

> **The lock-in problem:** Qdrant stores what your agent knows — learned
> preferences, resolved decisions, hard-won context — as opaque points with
> embeddings and payload dicts. Every backend writes a slightly different
> payload shape. Switch away and the knowledge is trapped in vectors you
> can't read. This showcase liberates it.

## What this does

```
┌──────────────┐   dump    ┌────────────────────┐   map_qdrant   ┌──────────────┐
│  Qdrant      │ ────────▶ │ provider export    │ ─────────────▶ │  Memanto     │
│  collection  │  scroll   │ export.json        │  (new mapper)  │  memories    │
└──────────────┘           └────────────────────┘                └──────┬───────┘
                                                                       │ export --okf
                                                                       ▼
                                                              ┌──────────────────┐
                                                              │ OKF bundle       │
                                                              │ (portable .md)   │
                                                              └──────────────────┘
```

The **new migration path** is a permanent addition:

- `memanto/cli/analyze/qdrant_export.py` — scrolls a Qdrant collection into
  the provider-style export JSON consumed by `memanto migrate --file`
- `map_qdrant` in `memanto/cli/migrate/mappers.py` — slots Qdrant payload
  fields onto the Memanto schema; unmapped fields are preserved in a
  `[Supporting data]` footer (bounded to ~800 chars, so nothing meaningful
  is dropped)
- `examples/migrations/qdrant-to-okf/` — lived-in seed data, the full
  runnable loop, and round-trip validation

## Quick start (zero infra, ~30 seconds)

```bash
pip install qdrant-client
python examples/migrations/qdrant-to-okf/run_migration.py
```

No Docker. No API keys. The seed uses Qdrant's embedded in-memory mode, so the
whole loop runs locally and is fully reproducible. Artifacts land in
`examples/migrations/qdrant-to-okf/output/`:

| Artifact | What it is |
| --- | --- |
| `export.json` | raw Qdrant collection dump (provider-style export) |
| `mapped_preview.jsonl` | mapped Memanto memory payloads |
| `okf_bundle/` | the OKF bundle — `index.md` + `memories/<type>/` |
| `roundtrip_report.md` | golden-QA recall parity report |

### Server-backed run (real production store)

```bash
docker run -p 6333:6333 qdrant/qdrant          # or use your existing instance
python examples/migrations/qdrant-to-okf/seed_qdrant.py --url http://localhost:6333
python -m memanto.cli.analyze.qdrant_export --url http://localhost:6333 \
    --collection memories --out export.json
memanto migrate --file export.json             # standard Memanto migrate flow
memanto memory export --okf                    # portable OKF bundle
```

## Payload conventions handled

Qdrant is a storage backend, so the exporter normalizes the common payload
shapes (in priority order) before the mapper runs:

| Shape | Used by | Recognized keys |
| --- | --- | --- |
| `text` + `metadata` | Mem0-on-Qdrant, custom memory backends | `text`, `metadata.created_at`, `memory_type`, `score`, `hash` |
| `page_content` + `metadata` | LangChain vectorstore | `page_content`, `metadata.tags` |
| bare attribute dicts | RAG chunks, custom stores | no text key → key/value pairs rendered as body |

### Mapping table (source → Memanto → OKF)

| Qdrant payload field | Memanto memory field | OKF frontmatter |
| --- | --- | --- |
| `text` / `content` / `memory` / `page_content` | `content` | body + `description` (first line) |
| `metadata.memory_type` / `type` / `category` / `kind` | `type` (coerced to Memanto vocabulary) | `type` |
| `metadata.created_at` / `timestamp` (ms or s epoch, or ISO) | `created_at` | `timestamp` |
| `metadata.tags` / `labels` / `categories` | `tags` | `tags` |
| point id | `source_ref` (`qdrant:<id>`) | `resource` |
| `metadata.source` | `source` | `x_memanto.source` |
| — (always) | `source: "qdrant"`, `provenance: "imported"` | `x_memanto.provenance` |
| everything else (`score`, `hash`, `run_id`, scope ids, vectors flag) | `[Supporting data]` footer | preserved in body footer |

Anything that doesn't map onto the schema is packed into a bounded
`[Supporting data]` markdown footer on the memory — searchable and visible,
and preserved through the OKF round trip (footer text stays in the body;
~800-char bound keeps memories readable).

## Round-trip validation

`run_migration.py` finishes with a golden-QA recall parity check: five
questions that are only answerable from the lived-in memory (where Tim lives,
the cat's name, the embedding store, the language preference, the coffee
order) are verified against the re-imported OKF bundle. Result on this
showcase: **5/5 (100%)**.

## Reproducibility

- `seed_qdrant.py` — generates the lived-in store (80 points, 6 weeks of
  memory, Mem0/LangChain/raw payload shapes) so the pipeline is reproducible
  end-to-end; the source data is *generated by a real Qdrant run*, not
  hand-written JSON
- `run_migration.py` — one command, full loop, prints the savings-style
  summary and type breakdown
- `requirements.txt` — `qdrant-client` only (the repo's own deps cover the
  rest)

## Savings report (this showcase)

| Metric | Qdrant (source) | Memanto (after) |
| --- | --- | --- |
| Source records | 61 points | — |
| Mapped memories | — | 61 (9 types) |
| Skipped / lost | — | 0 |
| Format | opaque JSON payloads + vectors | readable markdown + YAML frontmatter |
| Round-trip recall | — | 100% (5/5 golden QA) |

Refs #770
