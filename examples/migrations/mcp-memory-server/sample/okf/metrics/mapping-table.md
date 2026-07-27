# MCP Memory Server → Memanto OKF mapping

| MCP Memory concept | OKF representation | Memanto import behavior |
| --- | --- | --- |
| Entity name | `title` and H1 | Becomes the memory title |
| Entity type | Free-form OKF `type`, exact `mcp_memory.entity_type`, and `x_memanto.type` | Deterministically maps known semantic types; unknown types become `observation` without losing the source type |
| Observations | Numbered `## Observations` section | Imported as searchable memory content |
| Outgoing relation | Typed Markdown link in `## Relationships` | Link and relation label remain searchable |
| Incoming relation | Backlink in `## Relationships` | Graph neighborhood remains human-browsable |
| Exact source record | `json mcp-memory-source` fenced block | Survives import/export as memory content |
| Exact source file bytes | One base64 + SHA-256 manifest in the first entity block | Preserves whitespace, line endings, UTF-8 BOM, blank lines, and final-newline state |
| Source URI | `memory://knowledge-graph/entities/<name>` | Becomes `source_ref` |
| Provenance | `mcp-memory` tags and namespaced frontmatter | Preserved in tags/supporting data |

The original JSONL is also copied into `source/memory.jsonl`.  Import is scoped
to `memories/`, so the source and metrics directories are not re-ingested.
