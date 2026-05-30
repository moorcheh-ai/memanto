---
name: memanto-memory
description: Global memory companion that persists context across all skills. Use when work spans multiple tools, sessions, or skills. Stores decisions, preferences, and learnings, and recalls them when relevant.
---

# Memanto Memory

I am a cross-skill memory layer. I make sure nothing is forgotten between sessions and tools.

## Initialisation

At the start of every session, ensure Memanto is active:

```bash
python scripts/memanto_memory.py init
```

This creates or reuses a Memanto agent for the current project.

## Automatic Memory

Store a memory whenever you observe:
- **Decisions** — why a design choice was made
- **Preferences** — naming conventions, tools, libraries the user likes
- **Learnings** — bugs found, workarounds, architectural insights
- **Goals** — what the user is actively trying to achieve
- **Errors** — recurring issues and their fixes
- **Artifacts** — files created, modified, or deleted

```bash
python scripts/memanto_memory.py remember "title" "description of what happened"
```

## Context recall

Before starting a significant task, retrieve relevant context:

```bash
python scripts/memanto_memory.py recall "what we were working on"
```

## Direct questions

When the user asks about past work, answer from memory:

```bash
python scripts/memanto_memory.py answer "question here"
```

## Example workflow

```
# Session 1 — store decisions
→ python scripts/memanto_memory.py remember "Chose FastAPI" "Picked FastAPI over Flask for async support and built-in validation"

# Session 2 — recall before starting
→ python scripts/memanto_memory.py recall "API framework decision"
  → [decision] Chose FastAPI — Picked FastAPI over Flask for async…

# Session 3 — ask a question
→ python scripts/memanto_memory.py answer "why did we pick FastAPI?"
  → Chose FastAPI for async support and built-in validation
```
