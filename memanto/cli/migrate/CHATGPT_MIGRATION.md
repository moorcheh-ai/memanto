# ChatGPT → Memanto → OKF: The Freedom Loop

This migration showcase demonstrates the complete "own your memory" pipeline:
**ChatGPT data export → Memanto memories → portable OKF bundle.**

## Why ChatGPT?

ChatGPT is where millions of users have stored years of AI conversations —
personal insights, creative work, technical discussions, and hard-won
context. But that data is locked in OpenAI's export format. This showcase
proves it doesn't have to be.

## The Pipeline

```
ChatGPT export (conversations.json)
    │
    │  map_chatgpt (new mapper in mappers.py)
    ▼
Memanto memories (typed, searchable, agent-accessible)
    │
    │  memanto memory export --okf
    ▼
OKF bundle (portable markdown, git-friendly, human-readable)
    │
    │  memanto migrate okf ./bundle
    ▼
Any OKF-compatible system ✅
```

## Quick Demo

### 1. Export your ChatGPT data

Go to ChatGPT → Settings → Data Controls → Export Data.
You'll receive `conversations.json`.

### 2. Dry-run the migration

```bash
memanto migrate chatgpt --file conversations.json --dry-run
```

See exactly what will be imported — mapped memory count, type breakdown,
and a savings report.

### 3. Run the migration

```bash
memanto migrate chatgpt --file conversations.json
```

Every user-assistant turn-pair becomes a searchable, typed memory with:
- Conversation title preserved as tags
- Original timestamps preserved
- Source provenance tracked

### 4. Export to OKF

```bash
memanto memory export --okf
```

Your ChatGPT history is now a portable, git-friendly directory of markdown
files. Take it anywhere. No lock-in.

### 5. Prove portability

```bash
# Import into a fresh Memanto agent
memanto migrate okf ./memanto-exports/okf/my-agent

# Or view as plain markdown
cat memanto-exports/okf/my-agent/observation/*.md
```

## What This Adds

| Before | After |
|---|---|
| ChatGPT export is a dead JSON file | ChatGPT becomes a live migration source |
| Your AI history is locked | Your AI history is yours, forever |
| 4 migration sources (Mem0, Letta, Supermemory, OKF) | 5 migration sources (+ ChatGPT) |

## The Code

`map_chatgpt` in `memanto/cli/migrate/mappers.py`:
- Parses the ChatGPT export tree structure
- Pairs user messages with assistant responses chronologically
- Maps each pair to a Memanto memory with proper types, tags, and timestamps
- Preserves full conversation metadata in the searchable footer

## Engineering Value

This is NOT a standalone script that re-implements what the CLI already does.
It adds a **new migration provider** to Memanto's existing `memanto migrate`
pipeline — following the exact mapper contract established by `map_mem0`,
`map_letta`, and `map_supermemory`. Any user who has ever used ChatGPT can
now own their conversation history in Memanto.
