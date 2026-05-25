# /memanto-tdd

A Memanto-enhanced version of mattpocock's `/tdd` skill.

Before starting TDD, this skill automatically loads your engineering profile
from Memanto — architectural decisions, preferences, and past choices — so you
never have to re-explain them.

After completing a TDD cycle, key decisions are stored back to Memanto for
future skill sessions.

---

## PRE-HOOK: Load Engineering Profile

Before writing any tests, run:

```bash
python skills_memory.py pre tdd "$TASK"
```

This injects context like:
- Framework preferences (e.g., "prefer vitest over jest")
- Architecture decisions (e.g., "use repository pattern")
- Coding style rules (e.g., "TypeScript strict mode always")

If memories exist, prepend the output to your system prompt automatically.

---

## Core TDD Loop (mattpocock vertical-slice pattern)

**No horizontal slicing. One vertical slice at a time.**

### RED
Write ONE failing test that describes the first behavior.
- Test must fail for the right reason
- No implementation yet

### GREEN
Write the MINIMUM code to make the test pass.
- Resist over-engineering
- Apply recalled architecture decisions automatically

### REFACTOR
Clean up only if needed.
- Check recalled preferences before refactoring style

Repeat for the next behavior.

---

## POST-HOOK: Store Decisions

After the TDD session completes, store what was decided:

```bash
python skills_memory.py post tdd "Summary of what was built" \
  --decisions \
    "Used repository pattern for data access" \
    "Chose vitest for speed over jest" \
  --preferences \
    "Always colocate test files with implementation"
```

These decisions are now permanently available to ALL future skill executions.

---

## Memory-Aware Rules

1. **Apply recalled decisions immediately** — do not ask the developer to re-confirm preferences already in memory.
2. **Store new decisions** — if a new architectural choice is made during TDD, call the post-hook.
3. **Contradict carefully** — if a new decision contradicts a stored one, use `python skills_memory.py post` with the updated fact. The old fact is preserved in metadata for audit.
