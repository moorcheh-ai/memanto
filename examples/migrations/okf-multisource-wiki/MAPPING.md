# Source → Memanto / OKF mapping

This Path C showcase feeds the shipped `memanto migrate okf` CLI. Adapters
emit OKF markdown; Memanto's own `okf_loader` + `map_okf` perform the import.

## Chroma (`agent_long_term_memory` collection)

| Chroma concept | Memanto / OKF field | Notes |
| --- | --- | --- |
| point `id` | `resource` / `x_memanto` provenance + `chroma_id` extra | Preserved losslessly |
| `document` | OKF body / Memanto `content` | Primary memory text |
| `metadata.memory_type` | OKF `type` + `x_memanto.type` | Must be a Memanto type when possible |
| `metadata.categories` | OKF `tags` | Comma-split labels |
| `metadata.session` | tag `session:…` | Cross-session provenance |
| `metadata.created_at` | `generated.at` | ISO-8601 UTC |
| `metadata.supersedes` | consolidation input | Archived under `sessions/` |
| embedding vector | *not exported* | Ownership story: leave opaque floats behind |

## Proprietary SQLite (`agent_memories`)

| SQLite column | Memanto / OKF field | Notes |
| --- | --- | --- |
| `id` | `sqlite_id` + `resource` | |
| `body` | OKF body | |
| `kind` | OKF `type` (via kind map) | `constraint` → `instruction` |
| `thread_id` | tag `thread:…` | |
| `confidence` | `x_memanto.confidence` | |
| `created_at` | `generated.at` | |
| `meta_json` | tags / supporting extras | topic, related_incident, … |

## Consolidation rules

| Situation | Action |
| --- | --- |
| Exact duplicate text across stores | Single memory, `sources: [chroma, sqlite]` |
| Agreeing identity / timezone / on-call facts | Dedupe by topic key |
| Language preference correction in Chroma | Wins; archives Chroma original + SQLite stale preference |
| Unique facts (budget, CI, runbook, …) | Kept from originating store |

Superseded bodies are written under `sessions/superseded-timeline.md` so
`memanto migrate okf` (which scopes import to `memories/`) cannot revive them.
