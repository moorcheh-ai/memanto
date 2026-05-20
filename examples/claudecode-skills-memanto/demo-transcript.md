# Demo Transcript

This transcript shows the intended lifecycle for a Claude Code-style skill runner.

## Session 1: Architecture review stores a decision

Command:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py store \
  --skill grill-with-docs \
  --task "Review billing retry architecture" \
  --file src/billing/retries.ts \
  --transcript "Decision: Keep retry delays deterministic in tests. Preference: Error messages must name the upstream service and retry count. Must: Never retry non-idempotent POST requests unless the caller opts in."
```

Output:

```text
stored_memories=3
```

Three memories were distilled:
1. `[decision]` Keep retry delays deterministic in tests.
2. `[preference]` Error messages must name the upstream service and retry count.
3. `[instruction]` Never retry non-idempotent POST requests unless the caller opts in.

## Session 2: Later skill receives recalled context

Command:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py recall \
  --skill tdd \
  --task "Add invoice retry policy tests" \
  --file src/billing/retries.ts
```

Output:

```text
<memanto-engineering-memory>
Relevant prior engineering decisions:
- Keep retry delays deterministic in tests.
- Error messages must name the upstream service and retry count.
- Never retry non-idempotent POST requests unless the caller opts in.
</memanto-engineering-memory>
```

The `/tdd` skill now starts with the design constraints created during the separate `/grill-with-docs` review session. The developer does not need to repeat architectural instructions.

## Session 3: Full wrap lifecycle

Command:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py wrap \
  --skill tdd \
  --task "Implement retry handler" \
  --file src/retries.py \
  -- python -m pytest tests/test_retries.py
```

The wrapper:
1. Recalls prior memories and prints the context block.
2. Runs the test command.
3. Distills durable decisions from stdout/stderr and stores them.

## Environment variable injection

When `recall` runs, it also sets `MEMANTO_SKILL_CONTEXT` so child processes
(including the skill runner) can read the context without parsing stdout:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py recall ...
echo "$MEMANTO_SKILL_CONTEXT"
```
