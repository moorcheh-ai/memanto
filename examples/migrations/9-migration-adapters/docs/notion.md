# Notion export guide

## How to get your data

1. Open Notion and go to **Settings** (click your workspace name → Settings)
2. Select **Settings & Members** → **Settings**
3. Scroll to **Export content** → click **Export all workspace content**
4. Choose **Markdown & CSV** format
5. Click **Export** — Notion emails you a download link
6. Download and save the ZIP

## CLI command

```bash
memanto migrate notion --file path/to/notion_export.zip --agent <id>
```

Dry-run:

```bash
memanto migrate notion --file path/to/notion_export.zip --dry-run
```

Or use the convenience script:

```bash
# edit ZIP_PATH at the top, then:
python scripts/migrate_notion.py [--dry-run] [--agent <id>]
```

## Expected format

The ZIP contains `.md` files. Each file may have optional YAML frontmatter:

```markdown
---
title: My Page Title
tags: [rust, llm]
created_at: 2024-01-01
---

Page body content goes here.
```

Files without frontmatter are also supported — the filename stem is used as the title.
Files with empty bodies are skipped.

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| Markdown body (after frontmatter) | `content` | Stripped of the YAML block |
| `title` frontmatter or filename stem | `title` | Filename without extension as fallback |
| `tags` frontmatter | `tags` | List of strings |
| `created_at` frontmatter | `created_at` | Parsed via `_parse_dt` |
| hardcoded | `type` | `"artifact"` |
| hardcoded | `source` | `"notion"` |
| hardcoded | `provenance` | `"imported"` |
