# Source → Memanto / OKF Field Mapping

This table documents how concepts from each supported source tool map onto
`MemoryEntity` fields and the emitted OKF bundle (`memanto migrate okf`).

The adapter is **Path B** (unsupported-source migration): it transforms a raw
chat export into a valid OKF bundle, which `memanto migrate okf` imports
losslessly.

## Memory types (OKF `type` frontmatter)

All source adapters currently classify exported conversations as `context`
entries. `Memanto`'s OKF importer auto-classifies free-form `type` values on
import, so this is safe to leave broad at the export stage.

## Claude → OKF

| Claude export concept               | Claude JSON field        | MemoryEntity                  | OKF frontmatter  |
|-------------------------------------|--------------------------|-------------------------------|------------------|
| Conversation                        | `uuid` / `id`            | `metadata.chat_id`            | `x_memanto`      |
| Conversation title                  | `name`                   | `title`                       | `title`          |
| Conversation type                   | `type`                   | `metadata.conversation_type`  | `[Supporting data]` |
| Message (human + assistant)         | `chat_messages`/`messages`| `content` (paired)            | body             |
| Last activity timestamp             | `created_at`             | `timestamp`                   | `timestamp`      |
| —                                   | —                        | `tags=["claude", id]`          | `tags`           |
| —                                   | —                        | `confidence=0.85`             | `x_memanto`      |
| —                                   | —                        | `source_ref=claude://...`      | `resource`       |

## ChatGPT → OKF

| ChatGPT export concept        | ChatGPT JSON field       | MemoryEntity                 | OKF frontmatter  |
|-------------------------------|--------------------------|------------------------------|------------------|
| Conversation                  | `id` / `conversation_id` | `metadata.chat_id`           | `x_memanto`      |
| Conversation title            | `title`                  | `title`                      | `title`          |
| Message pairs (user/assistant)| `messages`/`mapping`     | `content`                    | body             |
| Message timestamp             | `create_time`            | `timestamp`                  | `timestamp`      |
| —                             | —                        | `tags=["chatgpt", id]`        | `tags`           |
| —                             | —                        | `source_ref=chatgpt://...`    | `resource`       |

## Gemini → OKF

| Gemini export concept          | Gemini JSON field      | MemoryEntity               | OKF frontmatter  |
|--------------------------------|------------------------|----------------------------|------------------|
| Conversation                   | `id` / `conversation_id`| `metadata.chat_id`         | `x_memanto`      |
| Conversation title             | `title`                | `title`                    | `title`          |
| Message (user + model)         | `messages`/`chat_messages`| `content` (paired)       | body             |
| Message timestamp              | `timestamp`/`created_at`| `timestamp`                | `timestamp`      |
| —                              | —                      | `tags=["gemini", id]`       | `tags`           |
| —                              | —                      | `source_ref=gemini://...`   | `resource`       |

## Notes

- **Fidelity:** unmapped source fields are preserved by `memanto migrate okf`
  in the `[Supporting data]` footer, so nothing is lost on import.
- **Round trip:** the same conversation can be recalled after import via
  `memanto recall` / `memanto answer` (see `validate_roundtrip.py`).
