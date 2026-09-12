# Hermes Holographic → Memanto / OKF mapping

This adapter migrates the **canonical SQLite fact store** from Hermes Holographic memory. It deliberately separates stored source truth from derived retrieval structures and query-time behavior.

| Hermes Holographic field | Native meaning | OKF / Memanto treatment | Fidelity class |
|---|---|---|---|
| `facts.content` | Canonical fact text | OKF body; imported as Memanto `content` | **PRESERVE** |
| `facts.category` | Holo classification (`user_pref`, `project`, `tool`, `general`, or other) | `user_pref → preference`; all other categories conservatively map to `fact`; original category remains in the source-data block | **TRANSFORM + PRESERVE RAW** |
| `facts.tags` | Source metadata string | Comma-separated values become OKF `tags`; unmodified raw string remains in source-data block | **TRANSFORM + PRESERVE RAW** |
| `facts.trust_score` | Holo trust signal, clamped to `[0,1]` | `x_memanto.confidence`; semantics are documented as analogous, not identical | **TRANSFORM** |
| `facts.created_at` | Source creation time | OKF `timestamp` in normalized UTC | **PRESERVE** |
| `facts.updated_at` | Source update time | `x_memanto.updated_at` in normalized UTC | **PRESERVE** |
| `facts.retrieval_count` | Operational source feedback | YAML source-data block in the Markdown body | **PRESERVE AS SOURCE METADATA** |
| `facts.helpful_count` | Operational source feedback | YAML source-data block in the Markdown body | **PRESERVE AS SOURCE METADATA** |
| `entities` | Entity records (`name`, `type`, aliases, creation time) | Structured list in the Markdown source-data block | **PRESERVE** |
| `fact_entities` | Fact ↔ entity association | Entity list is embedded with each fact | **PRESERVE** |
| `fact_id` | Stable ID inside one Holo DB | Preserved as source provenance in the body; not asserted to survive as a Memanto primary key | **PRESERVE AS PROVENANCE** |
| `facts_fts` | Derived FTS search index | Rebuilt by destination; never counted as portable knowledge | **REBUILD** |
| `facts.hrr_vector` | Derived HRR representation | Rebuilt/dropped; presence is recorded for accounting | **REBUILD** |
| `memory_banks.vector` | Derived aggregate HRR vector | Rebuilt/dropped; count is reported | **REBUILD** |
| relatedness / reasoning / contradiction queries | Query-time or inferred behavior | Tested through recall probes; not serialized as nonexistent durable graph/history records | **VALIDATE, DO NOT FABRICATE** |

## Why source metadata is in the Markdown body

Current Memanto OKF import preserves unknown frontmatter by folding it into a bounded `[Supporting data]` footer. A large custom `x_holo` frontmatter object could therefore be truncated after import. The adapter keeps critical Holo metadata in a compact, human-inspectable YAML block in the memory body, while using only standard OKF fields and Memanto's documented `x_memanto` extension for fields Memanto natively understands.

That choice has three properties important to this bounty:

1. humans can inspect the source metadata without a proprietary tool;
2. Memanto imports it as ordinary memory content, so it remains portable on export;
3. `validate.py` independently proves every represented source field survived.

## Claims deliberately not made

The public Holo schema does **not** contain a durable contradiction ledger, supersession chain, or first-class relationship-edge table. Entity adjacency exists through `fact_entities`; contradiction/relatedness behavior is query-time logic. This showcase therefore does not claim to migrate data structures that the source database does not actually store.
