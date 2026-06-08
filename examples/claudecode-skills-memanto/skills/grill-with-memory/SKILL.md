---
name: grill-with-memory
description: Grilling session enhanced with Memanto memory. Recalls past architectural decisions and domain terms before grilling, avoids re-asking resolved questions, and stores new decisions after. Use when the user wants to stress-test a plan while building on accumulated engineering knowledge.
---

# Grill with Memory

An enhanced version of `/grill-with-docs` that reads your past decisions before grilling and stores new ones after.

## Step 1 — Recall past decisions

Before grilling, retrieve what has already been decided:

```bash
memanto-skills recall grill-with-docs --hint "architecture decisions domain terminology ADR"
```

If memories are returned:
- **Do not re-ask questions already resolved** — if a memory says "we use CQRS for the order domain", don't ask "should we use CQRS?"
- Surface relevant past decisions when they affect the current plan: "You previously decided X — does this plan conflict with that?"
- If the plan contradicts a past `decision` memory, flag it explicitly before continuing.

## Step 2 — Run the grilling session

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore the codebase instead.

### Domain awareness

During codebase exploration, look for existing documentation:
- `CONTEXT.md` — domain glossary
- `docs/adr/` — past architectural decisions
- When a term conflicts with `CONTEXT.md`, call it out: "Your glossary defines X as Y — which is it?"
- When the user uses vague terms, propose precise canonical ones.
- Update `CONTEXT.md` inline as terms are resolved.
- Offer ADRs only when: (1) hard to reverse, (2) surprising without context, (3) result of a real trade-off.

## Step 3 — Store new decisions

After the session, store the key outcomes:

```bash
memanto-skills store grill-with-docs "SUMMARY" --type decision
```

Ask the user: "What decisions from this session should I save?" Store each one. Good candidates:
- Architectural choices and trade-offs made
- Domain term definitions agreed upon
- Constraints that apply to this area of the codebase
- Anything that would otherwise get re-asked in the next session
