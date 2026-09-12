# Mapping table — ChatGPT export → Memanto → OKF

Source: OpenAI Data Export (`conversations.json` + `memory.json`)

| ChatGPT concept | Source field | Memanto `type` | How mapped | OKF frontmatter field | OKF body |
|---|---|---|---|---|---|
| Explicit memory (memory.json) | `memory` string | via `type` or `classify()` → `preference`/`fact`/`goal` etc | `title` = first 80 chars, `content` = memory text, `tags` = `["chatgpt","memory.json"]`, `confidence` 0.78–0.88, `source_ref` = `id` | `type`, `title`, `description` (first 160 chars), `tags`, `timestamp`, `x_memanto.{id,confidence,source}` | `content` |
| Conversation turn (user message) | `mapping[].message.content.parts[0]` + `title`, `create_time`, `author.role` | `classify()` rule → `fact`/`preference`/`goal`/`decision`/`instruction`/`commitment`/`relationship`/`event`/`observation`/`learning`/`error`/`artifact`/`context` | `title` = `_title_from`, `content` = text + `[Supporting data]` footer (conv title, ids, role) bounded 800 chars, `tags` = `chatgpt` + `conv:<slug>` | same as above | `content` + footer (bounded 10k) |
| Assistant reply | `mapping[].message` with `role=assistant` | **Not migrated** — responses are not stored memory; only user-originated facts are migrated | skipped | — | — |
| Evolving preference (coffee→tea→water) | same fact across 3 timestamps | kept as 3 memories with `contradiction-resolved` tag on later entry | latest has `confidence` 0.88, earlier lower but preserved trail | `tags` includes `contradiction-resolved` | trail visible in markdown |
| Graph-like relationships | conversation threads linking Maya, Raj, Luna etc | `relationship` / `fact` with `tags` `conv:*` | preserved via supporting data + tags | `tags` | body |

**Memanto → OKF (shipped `OkfExportService`):**

| Memanto field | OKF field | Notes |
|---|---|---|
| `type` | `type` | one of 13 VALID_MEMORY_TYPES |
| `title` | `title` | ≤100 chars |
| `content` (first 160 chars) | `description` | truncated |
| `tags` | `tags` | array |
| `created_at` → ISO Z | `timestamp` / `generated.at` | UTC |
| `source_ref` | `resource` / `x_memanto.id` | original id |
| `confidence` | `x_memanto.confidence` | 0.55–0.88 |
| `source`=`chatgpt` | `x_memanto.source` | provider |
| `provenance`=`imported` | `x_memanto.provenance` | |

**Fidelity guarantee:** `sample-data/okf-bundle` → `memanto migrate okf ./sample-data/okf-bundle --dry-run` reloads **43/43** via `okf_loader` (verified in `run_migration.py`).

**Provider export shape fed to CLI:** `{"conversations": [...], "memories": [...]}` → `map_chatgpt()` → `list[dict]` matching `mappers.MAPPERS` contract. Also consumable as `memanto migrate --file export.json` if we emit `export.json` (adapter supports both).
