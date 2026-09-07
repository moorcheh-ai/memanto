# ChatGPT -> OKF: Own Your Agentic Memory

> **Path B / C showcase for [memanto #1609](https://github.com/moorcheh-ai/memanto/issues/1609).**
> The most viral freedom loop in agentic memory: take the memory ChatGPT built
> about you, and own it as plain, portable, git-friendly markdown.

## What this does

ChatGPT's official account export (`conversations.json`) is a graph of every
message across every conversation. Your own statements -- preferences, facts,
commitments, decisions -- are the highest-value memory you can carry out.

This adapter:

1. Parses the export and walks the **active branch** of every conversation
   (dead branches from regenerations and edits are skipped).
2. Extracts your **user-authored messages** as structured memory records.
3. Renders them as an **OKF bundle** -- one markdown file per conversation,
   with YAML frontmatter that round-trips back into Memanto via
   `memanto migrate okf`.

## Quick start

```bash
# 1. Export your ChatGPT data (Settings -> Data controls -> Export).
#    Unzip it and find conversations.json.

# 2. Generate the OKF bundle:
python3 export_okf.py /path/to/conversations.json ./chatgpt-okf

# 3. Preview the mapping (no writes):
memanto migrate okf ./chatgpt-okf --dry-run

# 4. Import into your agent:
memanto migrate okf ./chatgpt-okf --agent my-agent
```

## What you get

```
chatgpt-okf/
  memories/
    trip-planning-conv-2.md            # one file per conversation
    python-debugging-help-conv-1.md
```

Each memory is a self-contained markdown document with `type`, `tags`,
`generated` (`by` / `at`), `resource`, and an `x_memanto` block, following
the OKF v0.2 layout (frontmatter `okf_version: 0.2`, generated-at metadata
under `extra.generated.at` after import). The whole bundle is versionable in
git, human-readable, and importable anywhere that understands OKF.

## Also available as a first-class CLI command

The same adapter ships as `memanto migrate chatgpt` (dry-run supported):

```bash
memanto migrate chatgpt ./conversations.json --dry-run
memanto migrate chatgpt ./conversations.json --agent my-agent
```

This maps straight into Memanto's schema without the intermediate OKF files.

## Notes

- **Offline & network-free**: no OpenAI SDK, no network calls. Requires
  PyYAML (`pip install pyyaml`) -- it is part of Memanto's own dependencies.
  The adapter in `memanto/cli/migrate/chatgpt_export.py` is pure stdlib.
- **Bounded**: capped at 1000 conversations / 4000 chars per message so huge
  archives stay fast.
- **Type-aware**: `type` is left unset so Memanto's parsing service
  auto-classifies each statement (preference, fact, commitment...).
- System messages, assistant messages, and empty nodes are never imported.
