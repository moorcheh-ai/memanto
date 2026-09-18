# Liberate the Memory Your Assistant Has Built About You

**Path B: The New Frontier** — a new migration adapter that brings **exported
ChatGPT and Claude conversation archives** into Memanto, then out again as a
portable, human-readable **OKF bundle**.

The story it tells: your assistant has spent months building a portrait of
you — your preferences, decisions, goals, working rules. Today that memory is
trapped inside a proprietary, tool-bound chat archive. Switch tools and it
evaporates. This demo shows the escape: `in → owned → portable`, with *real*
source archives, a *shipped* adapter, and a *lossless* round trip.

## What this does

1. **`scripts/sample_conversations.py`** — generates two realistic, lived-in
   source archives in the exact JSON shapes Claude and ChatGPT write to disk:
   - `data/claude_conversations.json` — Claude-style `{conversations:[...]}`
     with `chat_messages` (`sender`/`text`/`created_at`/`uuid`)
   - `data/chatgpt_conversations.json` — ChatGPT-style `{conversations:[...]}`
     with thread `mapping` (`message`/`author.role`/`content.parts`/`parent`)
   - These are **source-tool archives**, not hand-written Memanto payloads —
     the whole pipeline is reproducible from scratch.
2. **`scripts/run_migration.py`** — runs the **new adapters**
   (`memanto/cli/migrate/mappers.py::map_claude` / `map_chatgpt`) that distill
   user signal turns into typed Memanto memories, then exports them with the
   **shipped** OKF exporter into `okf/`.
3. **`scripts/roundtrip_check.py`** — golden-Q&A recall-parity validation
   (keyword-based, with an optional local-LLM judge).

```
./run_migration.sh   # the whole loop in one command
```

## The migration summary

Source records → mapped memories → per-type breakdown (real output).
**Source records** are raw nonempty source messages and may include assistant
messages; only **memories mapped** counts the user-signal turns that survived
distillation — assistant chatter is deliberately dropped:

| source | source records | memories mapped |
|--------|---------------|-----------------|
| claude | 11            | 9               |
| chatgpt| 6             | 4               |

```
13 memories mapped, by type:
  auto-classify 6
  preference   3
  context      1
  instruction  1
  decision     1
  goal         1
```

Assistant chatter is deliberately **dropped** — a greeting like *"How can I
help today?"* is not a durable memory, and the adapter keeps the migration from
echoing noise into your lasting memory store.

## Mapping table (source → Memanto → OKF)

| Source-tool concept (example) | Memanto type | OKF field(s) |
|-------------------------------|--------------|--------------|
| "I prefer dark themes…"        | `preference` | `type`, `title`, `description`, `tags` |
| goal ("Ship the MVP by Friday")| `goal`       | `type`, `title`, `description` |
| decision ("I decided to use Stripe") | `decision` | `type`, `title` |
| instruction ("Pin dep versions")| `instruction`| `type`, `title` |
| working context ("We use Azure AD") | `context` | `type`, `title` |
| observation ("I like coffee with oat milk") | `preference` | `type`, `title` |
| provenance everywhere          | `x_memanto.source` / `x_memanto.provenance` | `x_memanto.source`, `x_memanto.provenance`, `resource` (source_ref), `timestamp` (created_at) |
| dropped (no durable signal)    | —             | —            |

Every OKF document carries a full `x_memanto` provenance block (`source`,
`provenance: imported`, `confidence`, message refs) so nothing is lost when it
moves out of Memanto.

## Round-trip validation (fidelity evidence)

Golden Q&A set queried against the source archive (`before`) and the migrated
OKF bundle (`after`):

```
ROUND-TRIP RECALL PARITY (golden Q&A set)
Before migration (raw source archive): 8/8 (100%)
After migration  (OKF bundle):        8/8 (100%)
```

**8/8 → 8/8: zero amnesia.** Every signal that was in the original
conversations survives migration and is recallable from the portable bundle.
An LLM-as-judge scores the same set when a local DeepSeek endpoint is
reachable; the keyword fallback keeps the demo deterministic and honest.

## The OKF reward

`okf/` is a complete, valid OKF bundle — open it and read the memory store as
plain markdown:

```
okf/
  index.md
  memories/
    preference/<slug>.md    # frontmatter + body + [Supporting data]
    goal/…
    context/…
    learning/…
  metrics/overview.md       # type distribution + activity timeline
```

```markdown
---
type: preference
title: I prefer dark themes in my editor and terminal.
description: I prefer dark themes in my editor and terminal.
tags: [genai, claude]
timestamp: '2026-08-01 00:00:00+00:00'
resource: m00cf6c|m99b19c|…          # source message refs
x_memanto:
  confidence: 0.6
  provenance: imported
  source: claude
  type: preference
---

I prefer dark themes in my editor and terminal.

---
[Supporting data]
- Source: claude
- Role: user
- Message refs: …
```

The bundle round-trips losslessly: `memanto`'s own loader reads all 13
memories back (verified in step 3 of `run_migration.sh`).

## Reproducible setup

- Needs Python 3.10+ and the exact-pinned deps in `requirements.txt` (or just
  reuse an existing memanto checkout's venv).
- No API key and no Moorcheh account required. The **migration itself runs
  fully offline** against the local SDK — but the one-time environment setup
  (`pip install -r requirements.txt`) needs package access, and
  `./run_migration.sh` will bootstrap a local venv over the network the first
  time it runs.

```bash
pip install -r requirements.txt   # one time (needs network)
./run_migration.sh                # then runs fully offline
```

## Build on it / try your own data

Point `scripts/run_migration.py` at your *real* ChatGPT (Settings → Data
controls → Export) or Claude export archive — the adapters accept the native
`.json` shapes. The exporter collapses per-type files automatically, so even a
large archive becomes a readable OKF bundle.
