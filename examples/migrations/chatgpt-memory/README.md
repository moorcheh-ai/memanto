# ChatGPT → OKF → Memanto

A migration adapter that extracts durable **user memories** out of a ChatGPT
conversation history, packages them as a portable [OKF](https://docs.memanto.ai/integrations/okf)
bundle, and hands them off to Memanto with:

```bash
memanto migrate okf ./chatgpt-memory/
```

## What this is for

When a chat assistant has been talking with you for weeks, it has quietly
built a model of *you* — preferences, the stack you run, the decisions you've
made. When that context window rolls off, or if you switch assistants, that
memory vanishes. This adapter makes that memory portable.

**What we do:** read a ChatGPT-style JSON export and emit a small set of
plain-Markdown OKF documents, one per durable user memory, tagged by category
(`preference`, `fact`, `decision`, `goal`).

**What we deliberately do not do:** dump every raw assistant turn. We extract
only the user-facing knowledge that's worth remembering, so the bundle stays
small, readable, and actually useful as a migration target.

## Quick start

```bash
# 1. Produce a ChatGPT-style export (your own tooling, or use the sample).
#    Expected shape: a JSON array of {"thread_id", "title", "messages": [...]}

# 2. Extract memories into an OKF bundle
python3 extract_memories.py chatgpt_export.json ./chatgpt-memory/

# 3. Inspect — plain Markdown with YAML frontmatter
cat ./chatgpt-memory/*.md

# 4. Import into Memanto (requires MOORCHEH_API_KEY in your environment)
memanto migrate okf ./chatgpt-memory/
```

## Run the sample end-to-end

This folder ships `sample_export.json` (3 realistic threads) and the script:

```bash
python3 extract_memories.py sample_export.json sample_bundle/
# -> 6 memory documents across preference / fact / decision / goal
```

Open any `.md` in `sample_bundle/` — it's valid OKF that Memanto's
`memanto migrate okf` importer reads losslessly.

## Input format

A JSON array of threads. Each thread is an object with:

| Key | Required | Example |
|---|---|---|
| `thread_id` | yes | `"thread-abc123"` |
| `title` | yes | `"Project planning session"` |
| `messages` | yes | `[{"role": "user", "content": "...", "timestamp": "2026-05-01T10:00:00Z"}, ...]` |

Only `role: "user"` messages are scanned; assistant replies are treated as
context and ignored. User messages under ~30 characters (greetings, one-liners)
are skipped.

## Output

One `.md` file per extracted memory, plus an `index.md` navigation file
(skipped by the importer). Each document has YAML frontmatter conforming to
OKF:

```yaml
---
type: preference
title: "I prefer Kotlin over Java."
tags:
  - preference
  - chatgpt-import
  - thread:thread-abc12
timestamp: "2026-05-01T10:00:00Z"
resource: chatgpt://thread/thread-abc123def456
x_memanto:
  type: preference
  source: chatgpt
---

Extracted from thread **Project planning session** (thread-abc123def).

First surfaced: `2026-05-01T10:00:00Z`

I prefer Kotlin over Java because the null-safety model keeps me sane...
```

## How it works

1. Walk every `user` message in every thread.
2. Classify with keyword/signal regexes (see `SIGNAL_PATTERNS` in
   `extract_memories.py`) into one of `preference`, `fact`, `decision`,
   `goal`. Messages with no strong signal are dropped.
3. Write each surviving memory as an OKF Markdown document with full
   provenance (`thread_id`, `timestamp`, `resource` URI).
4. De-duplicate identical bodies within the same thread so repeat utterances
   don't pollute the bundle.

The extraction is **fully deterministic and offline** — no LLM call — so the
same export always produces byte-stable output. Easy to review, easy to CI,
easy to prove round-trip fidelity.

## Reusability

This adapter lives in `examples/migrations/chatgpt-memory/` so it ships with
the repo and a reviewer can run it in under 15 minutes. The design follows
the pattern used by the existing provider adapters (`letta`, `mem0`,
`supermemory`): a thin script that emits an OKF bundle, which Memanto's
standard `memanto migrate okf` importer consumes.

To add another source (Zep, Graphiti, LangMem, LangGraph checkpoints), write
a companion `extract_<source>.py` that emits the same OKF shape and drop it
into this folder — the import step is already done.

## Testing

```bash
python3 -m pytest test_extract_memories.py -v
```

18 tests covering category inference, message filtering, deduplication, and
OKF frontmatter validity.
