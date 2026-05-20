# Demo Transcript

This transcript shows the intended lifecycle without requiring private
credentials.

## Session 1: architecture review

Command:

```bash
python examples/claudecode-skills-memanto/skill_memory.py before \
  --skill grill-with-docs \
  --task "Review API client retry strategy" \
  --paths "src/api/client.ts"
```

Result:

```text
Wrote .memanto-skill-memory/injected-context.md
```

The first run has no prior context. After review, the session summary says:

- Decision: Keep retries in the transport adapter instead of feature modules.
- Preference: Error messages should name the upstream service and retry count.
- Must: Do not retry non-idempotent POST requests unless the caller opts in.

Store it:

```bash
python examples/claudecode-skills-memanto/skill_memory.py after \
  --skill grill-with-docs \
  --task "Review API client retry strategy" \
  --paths "src/api/client.ts" \
  --transcript .memanto-skill-memory/session.md
```

## Session 2: implementation

Command:

```bash
python examples/claudecode-skills-memanto/skill_memory.py before \
  --skill tdd \
  --task "Implement API client retry handling" \
  --paths "src/api/client.ts"
```

Expected injected context:

```text
- [decision] Keep retries in the transport adapter instead of feature modules.
- [preference] Error messages should name the upstream service and retry count.
- [instruction] Do not retry non-idempotent POST requests unless the caller opts in.
```

The implementation skill now starts with the design constraints that were
created during the separate review skill run.
