# Hindsight → Memanto → OKF mapping

Source schema: Hindsight transfer archive v1 (`manifest.json`, `documents/*.json`,
optional `observations.json`).

| Hindsight field | Memanto memory field | OKF field |
|-----------------|----------------------|-----------|
| `TransferFact.text` | `content` (title derived from first 80 chars) | body |
| `TransferFact.fact_type` | `type` via `HINDSIGHT_FACT_TYPE_MAP` | `x_memanto.type` when mapped |
| `TransferFact.tags` + document `tags` | `tags` (+ `hindsight:{fact_type}`) | `tags` |
| `TransferFact.context` | appended to `content` | body |
| `TransferFact.entities` | appended to `content` | body |
| `TransferFact.causal_relations` | appended to `content` | body |
| `TransferFact.mentioned_at` / `occurred_start` / `event_date` | `created_at` | `timestamp` / `x_memanto` |
| `document.id` + fact index | `source_ref` (`{doc_id}#{index}`) | `x_memanto.source_ref` |
| `TransferObservation.text` | `content`, `type=observation` | body + type |
| Unmapped Hindsight metadata | `[Supporting data]` via `map_okf` on import | `extra` frontmatter |

## `fact_type` mapping

| Hindsight `fact_type` | Memanto type |
|-----------------------|--------------|
| `world` | `fact` |
| `experience` | `event` |
| `opinion` | `preference` |
| `observation` | `observation` |
| `belief` | `fact` |
| `relationship` | `relationship` |
| `goal`, `plan` | `goal` |
| `task` | `commitment` |
| `decision` | `decision` |
| (unknown) | auto-classify (`type=None`) |

## Lossless fields

Embeddings and database IDs are **not** present in Hindsight exports (by
design). All textual facts, tags, entities, causal relation metadata, and
observation source pointers are preserved in OKF content or supporting footers.
