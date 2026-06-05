---
name: memanto-skill-companion
description: Use when running Claude Code slash skills that should preserve decisions, preferences, project facts, or lessons across future skill executions.
---

# MEMANTO Skill Companion

MEMANTO should sit around slash-skill work, not inside one isolated command.
Before executing a skill, read the injected `<memanto-skill-context>` block and
apply those memories as prior engineering context. After the skill finishes,
make important outcomes explicit in the transcript so the stop hook can capture
them.

## Memory-Friendly Transcript Markers

Use these labels for durable outcomes:

| Marker | MEMANTO type |
| --- | --- |
| `Decision:` | `decision` |
| `User preference:` | `preference` |
| `Codebase fact:` | `fact` |

## Example

```text
Decision: keep token refresh inside the auth service because it owns retry policy.
User preference: prefer concise error messages in UI copy.
Codebase fact: API routes live under src/server/routes and use zod schemas.
```

Only label durable engineering context. Do not label routine progress updates,
scratch thoughts, or facts that will be stale by the next session.
