# Graphiti → Memanto mapping table

> The concept and field sections below are the approved mapping. Per-run
> counts at the bottom are filled automatically by
> `scripts/graphiti_to_memanto.py` from the real export — they are empty
> tonight because the live Graphiti populate was blocked (see `BLOCKERS.md`).

## 1. Concept mapping

| Graphiti concept | Memanto type | Why |
| --- | --- | --- |
| `EntityEdge` | `fact` (default), refined to `preference` / `decision` / `goal` / `commitment` / `instruction` / `relationship` / `event` / `error` | Graphiti's atomic unit of knowledge and the only object carrying `valid_at`/`invalid_at`. The relation name (`PREFERS`, `DECIDED_ON`, `WORKS_AT`) is a strong signal for a more specific Memanto primitive than a bare `fact`. |
| `EntityNode` | `context` | A durable subject with a rolled-up summary of everything around it — background about a recurring participant, not a discrete assertion. |
| `EpisodicNode` | `observation` | The raw ingested utterance. Unprocessed testimony rather than derived knowledge, so `observation` is the honest primitive. |
| `CommunityNode` | `learning` | Not observed — Graphiti synthesises it by clustering the graph and summarising each cluster. That derived quality is what separates `learning` from `fact`. |

## 2. Field mapping

| Graphiti field | Lands in | Notes |
| --- | --- | --- |
| `fact` / `summary` / `content` | memory body | Verbatim; first line reused as the OKF `description`. |
| `uuid` | `resource` / `source_ref` | Prefixed `graphiti:<kind>:<uuid>` so every memory traces back to one graph object. |
| `valid_at` | `timestamp` → `created_at` | **Valid time wins over transaction time.** |
| `invalid_at` | body sentence + `invalid_at` frontmatter | Preserved twice: prose so retrieval can match it, frontmatter so import is lossless. |
| `expired_at` | body sentence + `expired_at` frontmatter | When Graphiti itself decided the fact was contradicted. |
| `created_at` | `ingested_at` frontmatter | Transaction time, kept distinct from valid time. |
| `name` (relation) | type heuristic + `relation:<name>` tag | Drives the refinement from `fact` to a more specific type. |
| `source_node_uuid` / `target_node_uuid` | `Graph relation: A -[REL]-> B` line in the body | Memanto stores no inter-memory edges, so the triple is flattened into readable text rather than dropped. |
| `episodes` | `graphiti_episodes` count | How many source episodes support the fact. |
| `group_id` | `graphiti_group_id` frontmatter | Partition provenance. |
| `labels` | `label:<name>` tags | Entity typing from Graphiti's ontology. |
| `attributes` | `Attributes:` line in the body | Custom entity attributes, flattened to text. |
| `name_embedding` / `fact_embedding` | _dropped_ | Model-specific; Memanto re-embeds on ingest. |

## 3. Confidence policy

| Record | Confidence |
| --- | ---: |
| Entity edge, still valid | 0.9 |
| Entity edge, superseded | 0.5 |
| Entity node (`context`) | 0.8 |
| Episode (`observation`) | 0.7 |
| Community (`learning`) | 0.6 |

## 4. What this run actually produced

_Not yet filled — awaiting a live `scripts/graphiti_to_memanto.py` run against
a real `data/graphiti_raw_export.json`. See `BLOCKERS.md`._

## 5. Where the temporal interval survives

1. **Prose in the memory body** — so Memanto retrieval can match on it.
2. **OKF frontmatter keys** — `valid_at`, `invalid_at`, `expired_at`,
   `ingested_at`, `graphiti_status`. `memanto migrate okf` routes unknown
   frontmatter into the `[Supporting data]` footer.
3. **Tags** — `current` / `superseded`.
