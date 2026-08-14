# CrewAI unified memory to OKF mapping

This adapter targets the schema written by CrewAI 1.15.12's public `Memory`
API and `LanceDBStorage`. It does not claim that the older
`long_term_memory_storage.db` SQLite layout is the current unified-memory
format.

| CrewAI unified-memory field | OKF / Memanto destination | Fidelity rule |
|---|---|---|
| `id` | `resource: crewai://unified-memory/<id>` and `crewai.id` | Exact |
| `content` | Markdown body | Exact unless `--redact-secrets` is explicit |
| `scope` | `crewai.scope` and normalized `scope-*` tags | Exact in extension; tags aid filtering |
| `categories` | OKF `tags`, `crewai.categories`, and type inference | Exact in extension; normalized copy in tags |
| `metadata` | `crewai.metadata` | Exact nested YAML value |
| `importance` | `crewai.importance` and `x_memanto.confidence` | Exact original; confidence is the nearest 0–1 destination ranking signal |
| `created_at` | OKF `timestamp` | UTC-normalized, same instant |
| `last_accessed` | `crewai.last_accessed` | UTC-normalized, same instant |
| `source` | `crewai.source`; destination writer is `x_memanto.source: crewai` | Exact source retained; safe filter token used by Memanto |
| `private` | `crewai.private` and optional `visibility-private` tag | Exact; private records are excluded unless `--include-private` is explicit |
| `vector` | Not exported | Deliberately omitted derived data; embedding model and dimensions are destination-specific |

## Type precedence

The adapter selects the first valid Memanto type from:

1. `metadata.memory_type`
2. CrewAI categories
3. scope components
4. `observation` fallback

The aliases `incident`/`failure` → `error`, `insight`/`lesson` → `learning`,
`output` → `artifact`, and `rule` → `instruction` are explicit. The chosen
type and its basis are recorded in the manifest for auditability.

## Proof of preservation

Each source record is canonicalized without its model-specific vector and
hashed with SHA-256. The hash is written into both the OKF document and the
migration manifest. `validate.py` reconstructs the CrewAI record only from
the OKF loader's output and requires the source, declared, and reconstructed
hashes to match. It also passes every document through Memanto's shipped
`load_okf_bundle` and `map_okf` functions.
