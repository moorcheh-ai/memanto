# Graphiti → Memanto / OKF mapping

| Graphiti concept | Example | Memanto `type` | OKF notes |
| --- | --- | --- | --- |
| Entity node | `Alex Rivera` | `context` (person/org) or `artifact` | `resource=graphiti:entity:<uuid>`, tags include labels |
| Edge / fact triple | `(Alex)-[PREFERS]->(aisle seat)` | rule-based: `preference` / `fact` / `decision` / `commitment` / `goal` / `instruction` / `relationship` / `event` / `artifact` | body = natural-language fact + `Graph relation:` line |
| Edge with `invalid_at` | vegetarian superseded | prior → `observation` + `superseded` tag; new edge → `preference` + `provenance=corrected` | `valid_at` / `invalid_at` in body + `[Supporting data]` |
| Episode (selected) | refundable policy, PT instruction, delay ops note, card error | `decision` / `instruction` / `observation` / `error` / `commitment` / `goal` | raw chat fluff skipped; keep policy beats |
| Embeddings | — | **drop** | re-embed on Memanto ingest |
| `group_id` | `mira-travel-agent` | — | `tags=[group:…]` on every memory |

## Relation lexicon (`adapter.py`)

| Relation | Type |
| --- | --- |
| `PREFERS`, `PREFERS_CARRIER` | preference |
| `DECIDED` | decision |
| `COMMITTED_TO` | commitment |
| `HAS_GOAL` | goal |
| `INSTRUCTS` | instruction |
| `PARTNER_OF`, `REPORTS_TO`, `WORKS_AT` | relationship |
| `LIVES_IN` | fact |
| `TRAVELED_TO`, `EXPERIENCED` | event |
| `USES` | artifact |

## Provenance

- Default import: `imported`
- Replacement after invalidation: `corrected`
- Confidence: 0.9 valid edges, 0.5 superseded, 0.8 entities, 0.7 episodes
