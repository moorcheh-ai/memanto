---
name: memanto-store
description: Persist an engineering insight, decision, or preference into your Memanto cross-session memory. Use after any skill run to capture what was decided, learned, or discovered so future sessions inherit it automatically.
argument-hint: "The insight to store, e.g. 'Always use pytest-asyncio for async tests in this project'"
---

# Memanto Store — Save Engineering Insights

Capture an engineering insight from this session into your persistent Memanto profile.

## When an argument is provided

Store the argument directly:

```bash
memanto-skills store "${CURRENT_SKILL:-general}" "${ARGUMENT}" --type learning
```

Confirm to the user: `Stored: <memory_id>`. Done.

## When no argument is provided

Ask the user:

1. "What insight, decision, or preference should I save?" (wait for answer)
2. "What type best describes it?" — offer these choices:
   - `decision` — an architectural or technical choice made
   - `instruction` — a rule or convention to always/never follow
   - `preference` — a style or tool preference
   - `learning` — something discovered or learned (default)
   - `fact` — a fixed truth about the codebase or domain
   - `goal` — an objective for the project or session

Then run:

```bash
memanto-skills store "${CURRENT_SKILL:-general}" "${SUMMARY}" --type "${TYPE}"
```

## After storing

Confirm: `Stored memory <id> of type <type>. It will be injected in future sessions.`

Tell the user they can view their full profile with `/memanto-profile`.
