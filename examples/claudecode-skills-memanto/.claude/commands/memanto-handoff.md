# /memanto-handoff

Memanto-enhanced `/handoff`. Compacts the conversation into a handoff doc
AND ensures the next agent's `SessionStart` hook loads the full engineering
profile before they read a single line.

## Automatic behavior (via hooks)

- **SessionStart** (next agent): recalls the complete engineering profile —
  not just what's in this conversation thread
- **Stop** (this session): stores the handoff summary plus any open questions
  as `commitment`-type memories so they surface in future recalls

## Handoff document structure

1. **Current state** — what's done, what's broken, test status
2. **Engineering profile** — auto-populated via `answer.generate()` RAG
   summary of all stored decisions
3. **Next steps** — concrete, unambiguous
4. **Open questions** — stored as memories for `/grill-with-docs` to resolve
