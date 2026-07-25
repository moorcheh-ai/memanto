# Open WebUI to Memanto via OKF

This adapter converts Open WebUI's built-in **Settings > Data Controls > Export
Chats** JSON into a portable Open Knowledge Format bundle. It requires no
Open WebUI server, API token, or Memanto key.

## Why branch selection matters

Open WebUI stores a conversation as a message graph. Regenerating or editing a
response leaves abandoned sibling branches in `history.messages`, while
`history.currentId` identifies the branch visible to the user. Importing every
message would preserve contradictory answers that the user deliberately
discarded. This adapter walks from `currentId` to the root and migrates only
that selected branch.

If an older export lacks `currentId`, the newest terminal message is selected
deterministically. Broken parent references and cycles fail closed instead of
silently producing a partial transcript.

## Run

```bash
python examples/migrations/open_webui/adapter.py \
  ~/Downloads/chat-export-123.json \
  ./open-webui-okf

memanto migrate okf ./open-webui-okf --dry-run
memanto migrate okf ./open-webui-okf --agent my-agent
memanto memory export --okf --agent my-agent
```

The output contains one `artifact` memory per non-empty conversation and a
`migration-manifest.json` with exact chat/message counts. Each OKF document
retains the source chat ID, source message IDs, model names, timestamps, and
Open WebUI tags in frontmatter. Message bodies remain plain Markdown and can be
inspected or versioned before import.

## Mapping

| Open WebUI | OKF / Memanto |
| --- | --- |
| chat title | `title` |
| selected message graph | artifact Markdown body |
| chat creation time | `timestamp` |
| `meta.tags` | `tags` |
| message model | `source_models` |
| chat/message IDs | `source_chat_id`, `source_message_ids` |
| provider provenance | `x_memanto.source: open-webui` |

Attachments and generated binary assets are not embedded because the standard
chat export does not contain their bytes. Their textual references remain in
message content.
