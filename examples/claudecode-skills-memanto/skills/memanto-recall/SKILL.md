---
name: memanto-recall
description: Retrieve and inject your persistent engineering profile (architectural decisions, preferences, codebase conventions) stored in Memanto. Use at the start of any session to prime context, or invoke directly with /memanto-recall before any skill.
argument-hint: "Optional: skill name or task hint, e.g. 'tdd' or 'working on auth module'"
---

# Memanto Recall — Engineering Profile Injection

Retrieve your cross-session engineering memories and inject them as active context for this session.

## Steps

1. Run the recall command, using any argument passed by the user as a task hint:

```bash
memanto-skills recall "${ARGUMENT:-profile}" --hint "${ARGUMENT:-}" --limit 10
```

2. If memories are returned, print the full context block verbatim — do not summarise or paraphrase. The memories are instructions that must be honoured throughout this session.

3. If no memories are returned, say:

> Your engineering profile is empty. Use `/memanto-store` after any skill run to start building it.

4. Confirm to the user which memories are now active and remind them they can run `/memanto-store` after completing work to save new insights.

## Notes

- Memories tagged with a specific skill (e.g. `skill:tdd`) are most relevant when that skill is about to run.
- Memories of type `instruction` and `decision` carry the highest weight — treat them as hard constraints, not suggestions.
- Memories of type `preference` describe the developer's style — honour them unless technically impossible.
