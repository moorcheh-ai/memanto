# Phase 0 notes — schemas and conventions (read before coding)

## (a) Memanto provider-JSON / memory payload schema

What `SdkClient.batch_remember` (and therefore every `memanto migrate`
mapper) accepts, from `memanto/cli/migrate/mappers.py`:

| Field | Type | Notes |
| --- | --- | --- |
| `title` | str | Truncated from content if absent |
| `content` | str | ≤ 10_000 chars; may carry a `[Supporting data]` footer |
| `type` | str \| None | One of the 13 primitives, or `None` → auto-classify |
| `tags` | list[str] | Free-form |
| `confidence` | float | 0–1 |
| `source` | str | Provider name (`"mem0"`, `"letta"`, …) |
| `source_ref` | str | Original record id |
| `provenance` | str | `"imported"` for migrations |
| `created_at` | datetime | Original source timestamp when present |
| `updated_at` | datetime | Migration time |

The 13 valid types: `fact`, `preference`, `goal`, `decision`, `artifact`,
`learning`, `event`, `instruction`, `relationship`, `context`,
`observation`, `commitment`, `error`.

**CLI surface tonight:** `mem0` / `letta` / `supermemory` / `okf`. There is
**no** `graphiti` provider. `--file` loads a previously-produced provider
export; `--dry-run` always writes `mapped_preview.json` + the savings
report; `--report` writes the report on a real run. OKF import takes a
path, needs no API key, produces no savings report.

## (b) OKF bundle layout and `--split` modes

From `memanto/app/services/okf_export_service.py` and the docs:

```
<bundle>/
  index.md
  memories/                 # importable; migrate okf scopes here when present
    <type>/
      index.md
      <slug>.md             # or <type>.md when stacked
  daily-summaries/          # export-only context
  sessions/
  metrics/
```

Each document:

```yaml
---
type: fact
title: …
description: …          # first line of content
tags: […]
timestamp: …            # ← created_at on import
resource: …             # ← source_ref on import
x_memanto:
  confidence: …
  provenance: …
  source: …
  type: fact            # round-trip type
# any other key → preserved as "extra" → [Supporting data] footer
---
body…
```

`--split`:

| Value | Behavior |
| --- | --- |
| `auto` (default) | One file per memory; a type with >50 memories collapses to one stacked file |
| `file` | Always one file per memory |
| `type` | Always one stacked file per type (`<!-- okf-entry -->` sentinel) |

## (c) Graphiti concepts → Memanto types (the mapping we approved overnight)

See `data/mapping_table.md` and `DECISIONS.md`. Headline: EntityEdge→fact
(refined), EntityNode→context, EpisodicNode→observation,
CommunityNode→learning. Temporal intervals preserved in body + frontmatter
+ tags. Confidence from temporal standing.

## Repo conventions observed

- `/examples/migrations/` did **not** exist on `main` (only
  `examples/benchmarks/*`, `examples/langgraph-memanto`, etc.).
- Existing examples use: `README.md` + `requirements.txt` + `.env.example` +
  `.gitignore` + a single entry script + `tests/` + checked-in `results/`.
- This submission follows that shape under the bounty-specified path
  `examples/migrations/graphiti-to-okf/`.
