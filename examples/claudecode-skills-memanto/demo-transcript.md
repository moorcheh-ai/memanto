# Demo Transcript

This transcript uses the credential-free local backend. The same lifecycle works
with `MEMANTO_SKILL_BACKEND=memanto` when `MOORCHEH_API_KEY` is configured.

## Session 1: Skill Stores An Engineering Decision

```bash
$ export MEMANTO_SKILL_BACKEND=local
$ memanto-skill-memory wrap --skill grill-with-docs \
    --prompt "Review service boundaries" -- \
    python -c "print('Decision: keep HTTP clients in src/services so components stay framework-only.')"
Decision: keep HTTP clients in src/services so components stay framework-only.
```

Stored local record:

```json
{
  "memory": {
    "memory_type": "decision",
    "title": "Keep HTTP clients in src/services",
    "content": "keep HTTP clients in src/services so components stay framework-only",
    "tags": ["grill-with-docs", "project:/workspace/app"]
  }
}
```

## Session 2: Fresh Skill Receives The Prior Context

```bash
$ memanto-skill-memory pre --skill tdd \
    --prompt "Add tests for the new API client" \
    --cwd /workspace/app
## Memanto engineering memory

Relevant prior decisions and constraints recalled before this skill run:
- [decision] Keep HTTP clients in src/services: keep HTTP clients in src/services so components stay framework-only (Source: grill-with-docs, score: 3.90)
```

The new skill run does not need the user to repeat the architecture decision.
The same text is also available to wrapped commands through
`MEMANTO_SKILL_CONTEXT` and `.memanto-skills/last_context.md`.
