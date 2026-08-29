# Claude export guide

## How to get your data

1. Sign in to [claude.ai](https://claude.ai)
2. Click your initials in the lower-left corner → **Settings**
3. Navigate to **Privacy**
4. Click **Export data**
5. Anthropic emails you a download link (expires after 24 hours)
6. Download the ZIP — it contains `conversations.json`

Only available for Free, Pro and Max individual accounts.
Team/Enterprise data must be exported by the organization's Primary Owner.

## CLI command

```bash
memanto migrate conversations path/to/claude_export.zip --source claude --agent <id>
```

Dry-run preview:

```bash
memanto migrate conversations path/to/claude_export.zip --source claude --dry-run --report
```

Or use the convenience script:

```bash
# edit ZIP_PATH at the top, then:
python scripts/migrate_claude.py [--dry-run] [--agent <id>]
```

## Expected output shape

```json
{
  "memories": [
    {
      "uuid": "conv-uuid",
      "name": "Conversation name",
      "created_at": "2024-01-01T00:00:00Z",
      "chat_messages": [
        { "uuid": "msg-uuid", "sender": "human", "text": "hello", "created_at": "2024-01-01T00:00:00Z" },
        { "uuid": "msg-uuid-2", "sender": "assistant", "text": "hi", "created_at": "2024-01-01T00:00:01Z" }
      ]
    }
  ]
}
```

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `chat_messages[].text` | `content` | Only `sender == "human"`, non-empty; falls back to `chat_messages[].content[].text` when `text` is empty |
| `name` | `title` | Conversation name |
| `chat_messages[].created_at` | `created_at` | Parsed via `_parse_dt` |
| hardcoded | `source` | `"claude"` |
| hardcoded | `provenance` | `"imported"` |
| hardcoded | `type` | `None` (auto-classified) |
