# Obsidian export guide


## How to get your data

No export step needed — point the CLI directly at your vault directory.

Your vault is the folder you open in Obsidian. It typically looks like:

```text
~/Documents/MyVault/
  ├── Note One.md
  ├── Projects/
  │   └── Project Notes.md
  └── ...
```

## CLI command

```bash
memanto migrate obsidian --file /path/to/your/vault --agent <id>
```

Dry-run:

```bash
memanto migrate obsidian --file /path/to/your/vault --dry-run
```

Or use the convenience script:

```bash
# edit VAULT_PATH at the top, then:
python scripts/migrate_obsidian.py [--dry-run] [--agent <id>]
```

## Expected format

All `.md` files in the vault are recursed. Each file may have YAML frontmatter:

```markdown
---
title: Note Title
tags: [rust, llm, open-source]
---

Note body content.
```

Files without frontmatter use the filename stem as the title.
Files with empty bodies after stripping frontmatter are skipped.

## Field mapping

| Source field | Memanto field | Notes |
|---|---|---|
| Markdown body (after frontmatter) | `content` | Stripped of the YAML block |
| `title` frontmatter or filename stem | `title` | Filename without extension as fallback |
| `tags` frontmatter | `tags` | List of strings |
| hardcoded | `type` | `"artifact"` |
| hardcoded | `source` | `"obsidian"` |
| hardcoded | `provenance` | `"imported"` |
