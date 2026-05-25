# /memanto-handoff

A Memanto-enhanced version of mattpocock's `/handoff` skill.

Compacts the current conversation into a handoff document AND stores it to
Memanto so the next agent — in any future session — already has your
engineering profile loaded before they read a single line.

---

## PRE-HOOK: Load Context for Handoff

Before writing the handoff document, run:

```bash
python skills_memory.py pre handoff "current task"
```

This ensures the handoff document reflects ALL past decisions — not just those
visible in the current conversation thread.

---

## Handoff Document Structure (memory-aware)

The handoff document must include:

### 1. Current state
What was just completed. What tests pass. What is broken.

### 2. Engineering profile (from Memanto)
Paste the output of:
```bash
python skills_memory.py recall "engineering decisions preferences"
```
This gives the next agent full context without reading the full conversation.

### 3. Next steps
Concrete, unambiguous next actions.

### 4. Open questions
Unresolved decisions that need grilling.

---

## POST-HOOK: Store Handoff as Artifact

```bash
python skills_memory.py post handoff \
  "Handoff: $SUMMARY" \
  --decisions \
    "Unresolved: $OPEN_QUESTION_1"
```

The handoff itself becomes a retrievable memory. Future sessions can recall
what was handed off and to whom.

---

## Memory-Aware Rules

1. The handoff document is NOT a substitute for Memanto — always run both.
2. Open questions stored as `decision` type memories signal unresolved areas to future agents.
3. The next agent should run `python skills_memory.py pre <skill> <task>` before starting.
