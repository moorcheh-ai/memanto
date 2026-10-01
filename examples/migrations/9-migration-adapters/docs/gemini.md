# Gemini export guide

## How to get your data

> Gemini conversation history lives under **My Activity**, not the "Gemini" product entry.
> Selecting the "Gemini" entry exports Gems (custom personas), not conversations.

1. Go to [takeout.google.com](https://takeout.google.com) and sign in
2. Click **Deselect all**
3. Scroll down and check **My Activity** (not "Gemini")
4. Click **"All activity data included"**
5. In the pop-up, click **Deselect all**
6. Scroll and check **Gemini Apps** — if it doesn't appear, Gemini Apps Activity may be off; enable it at [myactivity.google.com/product/gemini](https://myactivity.google.com/product/gemini) first
7. Click **OK** → **Next step**
8. Choose delivery method, `.zip` format, export once
9. Click **Create export** — Google emails you when ready (usually a few hours; link expires after 7 days)

## CLI command

```bash
memanto migrate conversations path/to/takeout-*.zip --source gemini --agent <id>
```

Dry-run preview:

```bash
memanto migrate conversations path/to/takeout-*.zip --source gemini --dry-run --report
```

Or use the convenience script:

```bash
# edit ZIP_PATH at the top, then:
python scripts/migrate_gemini.py [--dry-run] [--agent <id>]
```

## Supported Takeout formats

The CLI handles all three observed formats:

1. **`My Activity.json`** — flat JSON activity log with `"Prompted <text>"` title entries and a `time` field
2. **`My Activity.html`** — same data as HTML; the CLI parses `outer-cell` divs
3. **Native conversation JSON** — entries with `messages[{role, text}]` arrays

Malformed files are skipped; processing continues for the rest of the archive.

## Expected output shape (native format)

```json
{
  "memories": [
    {
      "id": "conv-id",
      "createdTime": "2024-01-01T00:00:00Z",
      "messages": [
        { "role": "user", "text": "question" },
        { "role": "model", "text": "answer" }
      ]
    }
  ]
}
```

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| `messages[].text` | `content` | Only `role == "user"`, non-empty |
| `_title_from(content)` per user message | `title` | Derived from each user message via `_title_from(content)` |
| `createdTime` | `created_at` | Parsed via `_parse_dt` |
| hardcoded | `source` | `"gemini"` |
| hardcoded | `provenance` | `"imported"` |
| hardcoded | `type` | `None` (auto-classified) |
