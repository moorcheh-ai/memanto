---
name: tdd-with-memory
description: Test-driven development enhanced with Memanto cross-session memory. Recalls past TDD decisions (test framework choices, mocking conventions, interface patterns) before starting, and stores new decisions after. Use when the user wants TDD with persistent memory of past engineering choices.
---

# TDD with Memory

An enhanced version of `/tdd` that automatically loads your past testing decisions and stores new ones.

## Step 1 — Recall engineering context

Before writing any tests, retrieve relevant memories:

```bash
memanto-skills recall tdd --hint "test-driven development testing conventions"
```

If memories are returned, read them carefully. They represent past decisions — honour them:
- `instruction` memories are **hard rules** (e.g. "always use pytest-asyncio for async tests")
- `decision` memories describe **chosen patterns** (e.g. "we use `InMemoryRepo` adapters at test seams")
- `preference` memories describe **style preferences** (e.g. "prefer `describe`/`it` style naming")

## Step 2 — Run TDD

Now run the full TDD workflow (from `/tdd`):

---

### Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't.

**Good tests** are integration-style: they exercise real code paths through public APIs. They describe _what_ the system does, not _how_ it does it.

**Bad tests** are coupled to implementation. They mock internal collaborators, test private methods, or verify through external means.

### Anti-Pattern: Horizontal Slices

**DO NOT write all tests first, then all implementation.** Use vertical slices:

```text
RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  ...
```

### Workflow

1. **Planning** — confirm interface changes, which behaviors to test, identify deep module opportunities. Get user approval.
2. **Tracer Bullet** — ONE test → ONE minimal implementation → passes.
3. **Incremental Loop** — repeat: one test at a time, minimal code only.
4. **Refactor** — after all tests pass: extract duplication, deepen modules, apply SOLID where natural.

### Checklist Per Cycle

```text
[ ] Test describes behavior, not implementation
[ ] Test uses public interface only
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```

---

## Step 3 — Store new decisions

After the TDD session, capture what was decided:

```bash
memanto-skills store tdd "SUMMARY_OF_DECISION" --type decision
```

Ask the user: "What testing decisions should I save for future sessions?" Then store each one. Good candidates:
- Test framework or library choices
- Mocking strategies (e.g. "we never mock the database — use an in-memory adapter")
- Naming conventions for tests
- Which seams are used as test entry points
- Any deviations from the standard TDD workflow
