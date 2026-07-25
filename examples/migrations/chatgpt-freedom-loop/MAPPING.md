# ChatGPT → Memanto → OKF Mapping Table

| ChatGPT concept | Source location | Memanto field | OKF field / layout |
|-----------------|-----------------|---------------|--------------------|
| Conversation title | `conversation.title` | `tags[]` as `session:{title}` + `topic:{slug}` | frontmatter `tags` |
| Conversation id | `conversation_id` / `id` | `source_ref` prefix + supporting data | `x_memanto.source_ref` |
| Message id | `message.id` | `source_ref` suffix `{conv}:{msg}` | `x_memanto.source_ref` |
| Author role | `message.author.role` | filter (`system`/`tool` skipped; user+assistant paired) | N/A (pre-filter) |
| Message text | `content.parts[]` | `content` (`Q:` / `A:` exchange) | markdown body |
| Multimodal parts | `content_type=multimodal_text` | text + `[image]` markers in `content` | markdown body |
| Message timestamp | `message.create_time` (epoch) | `created_at` (UTC) | frontmatter `created` |
| Conversation create time | `create_time` | fallback for `created_at` | frontmatter `created` |
| Migration time | wall clock at map | `updated_at` | frontmatter `updated` |
| Preference signals | heuristic on text | `type=preference` | `memories/preference/` |
| Decision signals | heuristic on text | `type=decision` | `memories/decision/` |
| Observation signals | heuristic on text | `type=observation` | `memories/observation/` |
| Ambiguous | no keyword hit | `type=None` (server auto-classify) | `memories/fact/` (demo default) |
| Provenance | constant | `provenance=imported` | `x_memanto.provenance` |
| Source platform | constant | `source=chatgpt` | `x_memanto.source` |
| Confidence | constant `0.75` | `confidence` | `x_memanto.confidence` |
| Branching edits | `children[]` siblings | first-child linearization | N/A (path choice) |
| Supporting metadata | title / turn / ids | `[Supporting data]` footer | retained in body |

## Round-trip semantics

1. **In:** `conversations.json` → `map_chatgpt` → Memanto payloads  
2. **Owned:** `memanto migrate chatgpt` ingests via `batch_remember`  
3. **Portable:** `memanto memory export --okf` writes markdown with `x_memanto` namespaced fields  
4. **Back:** `memanto migrate okf ./bundle` re-imports without dropping unmapped fields
