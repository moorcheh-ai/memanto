# ChatGPT export guide


## How to get your data

1. Sign in to [chat.openai.com](https://chat.openai.com)
2. Click your profile icon → **Settings**
3. Go to **Data controls**
4. Click **Export data** → confirm in the modal
5. OpenAI sends a download link by email (sometimes SMS); allow up to 24 hours for delivery. The link expires after 24 hours. Note: ChatGPT Business and Enterprise workspace accounts cannot use this export method.
6. Download and save the ZIP — it contains `conversations.json`

## CLI command

```bash
memanto migrate conversations path/to/chatgpt_export.zip --source chatgpt --agent <id>
```

Dry-run preview (no writes):

```bash
memanto migrate conversations path/to/chatgpt_export.zip --source chatgpt --dry-run --report
```

Or use the convenience script:

```bash
# edit ZIP_PATH at the top of the file, then:
python scripts/migrate_chatgpt.py [--dry-run] [--agent <id>]
```

## Expected output shape

```json
{
  "memories": [
    {
      "id": "conv-id",
      "title": "Conversation title",
      "create_time": 1700000000.0,
      "current_node": "node-id",
      "mapping": {
        "node-id": {
          "message": {
            "author": { "role": "user" },
            "content": { "parts": ["user text"] },
            "create_time": 1700000000.0
          },
          "parent": null,
          "children": ["next-node-id"]
        }
      }
    }
  ]
}
```

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `message.content.parts[]` (joined) | `content` | Only `role == "user"` nodes |
| `title` | `title` | Conversation title |
| `message.create_time` | `created_at` | Parsed via `_parse_dt` |
| hardcoded | `source` | `"chatgpt"` |
| hardcoded | `provenance` | `"imported"` |
| hardcoded | `type` | `None` (auto-classified) |
