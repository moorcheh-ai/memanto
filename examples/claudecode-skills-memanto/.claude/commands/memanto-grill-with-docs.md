# /memanto-grill-with-docs

A Memanto-enhanced version of mattpocock's `/grill-with-docs` skill.

Challenges your plan against the domain model AND against your own stored
engineering decisions. Stores all resolved architectural choices to Memanto
so future skill sessions inherit them automatically.

---

## PRE-HOOK: Load Prior Decisions

Before the grilling session, run:

```bash
python skills_memory.py pre grill-with-docs "$TOPIC"
```

The recalled context is prepended to the grilling prompt. This means the
interviewer already knows your past decisions and will challenge new proposals
against them — not re-ask settled questions.

---

## Grilling Protocol (memory-aware)

1. **Load recalled decisions** — treat them as settled. Do not re-grill on resolved choices.
2. **Challenge only NEW proposals** — focus grilling energy on unsettled areas.
3. **Update CONTEXT.md and ADRs** as decisions crystallise (standard mattpocock behavior).
4. **Identify new decisions** — note anything resolved during this session.

### Interview rules:
- One question at a time
- Force a concrete answer before moving on
- If the developer contradicts a stored decision, surface the conflict explicitly

---

## POST-HOOK: Store All Resolved Decisions

After grilling completes:

```bash
python skills_memory.py post grill-with-docs \
  "Architecture session: $(date +%Y-%m-%d) — topic: $TOPIC" \
  --decisions \
    "Decision 1 resolved during this session" \
    "Decision 2 resolved during this session" \
  --preferences \
    "Preference discovered during grilling"
```

Every resolved decision is now part of the permanent engineering profile.
Future `/tdd`, `/handoff`, and `/improve-codebase-architecture` sessions
will load these decisions automatically via their own pre-hooks.

---

## Memory-Aware Rules

1. Never re-grill on decisions already stored in Memanto.
2. Surface contradictions between new proposals and stored decisions immediately.
3. Always run the post-hook — this session's decisions are tomorrow's context.
