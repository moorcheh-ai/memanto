---
name: handoff-with-memory
description: Compact the current conversation into a handoff document AND persist key decisions to Memanto so the next agent session starts with full context automatically. Use when finishing a session and handing off to another agent or a future session.
argument-hint: "What will the next session be used for?"
---

# Handoff with Memory

An enhanced version of `/handoff` that also writes key session insights to Memanto, so the next session automatically inherits the engineering context — no manual context-pasting required.

## Step 1 — Extract session insights

Before writing the handoff document, identify what should be persisted:

1. What architectural decisions were made this session?
2. What conventions or rules were established?
3. What was learned about the codebase that will matter next time?
4. What preferences were expressed by the developer?

## Step 2 — Store insights to Memanto

For each insight identified, store it:

```bash
memanto-skills store handoff "INSIGHT" --type MEMORY_TYPE
```

Use these types:
- `decision` — architectural or technical choices
- `instruction` — rules and conventions to always follow
- `preference` — developer style or tool preferences
- `learning` — codebase knowledge discovered

## Step 3 — Write the handoff document

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to the temporary directory of the OS — not the current workspace.

Include:
- **Context** — what was being worked on
- **Decisions made** — key choices (these are also now in Memanto)
- **Current state** — what's done, what's in progress, what's next
- **Suggested skills** — which skills the next agent should invoke (suggest `/memanto-recall` first)
- **Memanto note** — tell the next agent: "Run `memanto-skills recall <skill>` or `/memanto-recall` at the start — past decisions are already stored and will be injected automatically."

Do not duplicate content already in PRDs, ADRs, or commits — reference them by path/URL.

Redact sensitive information (API keys, passwords, PII).

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

## Step 4 — Confirm

Tell the user:
- How many memories were stored
- Where the handoff document was saved
- That the next session will automatically inherit the engineering profile via `/memanto-recall`
