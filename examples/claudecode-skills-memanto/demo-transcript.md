# Demo Transcript

This transcript shows the intended lifecycle for a Claude Code-style skill runner.

## 1. First Skill Run Stores a Decision

Command:

```bash
python examples/claudecode-skills-memanto/memanto_skills_hook.py post \
  --skill grill-with-docs \
  --task "Review billing retry architecture" \
  --file src/billing/retries.ts \
  --transcript "Keep retry delays deterministic in tests. Preserve idempotency keys across retries."
```

Output:

```text
stored_memories=1
```

Stored memory:

```text
Skill `grill-with-docs` handled task `Review billing retry architecture`.
Files in scope: src/billing/retries.ts.
Outcome and decisions: Keep retry delays deterministic in tests. Preserve idempotency keys across retries.
```

## 2. Later Skill Run Receives Relevant Context

Command:

```bash
python examples/claudecode-skills-memanto/memanto_skills_hook.py pre \
  --skill tdd \
  --task "Add invoice retry policy tests" \
  --file src/billing/retries.ts
```

Prompt context emitted for the next skill:

```text
<memanto-engineering-memory>
Relevant prior engineering decisions for this skill run:
- Keep retry delays deterministic in tests.
- Preserve idempotency keys across retries.
</memanto-engineering-memory>
```

The next `/tdd` skill can now align with prior project decisions without the developer repeating the same instructions.
