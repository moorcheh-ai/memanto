# Demo transcript

This transcript uses the local preview backend, so it is safe to run without
Moorcheh credentials. Live mode uses the same lifecycle with
`--backend memanto` after `memanto agent create` or `memanto agent activate`.

## 1. A review skill stores a durable decision

```bash
python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  post \
  --skill grill-with-docs \
  --task "Review billing retry architecture" \
  --file src/billing/retries.ts \
  --cwd /repo/payments \
  --transcript "Decision: keep retry delays deterministic in tests. Preserve idempotency keys across retries."
```

Output:

```text
stored_memories=1
```

Stored JSONL memory:

```json
{
  "memory_type": "decision",
  "source_skill": "grill-with-docs",
  "tags": [
    "claudecode-skills-memanto",
    "skill:grill-with-docs",
    "file:retries.ts",
    "path:src/billing",
    "project:payments"
  ],
  "content": "Skill `grill-with-docs` completed task `Review billing retry architecture`. Files in scope: src/billing/retries.ts. Durable engineering memory: Decision: keep retry delays deterministic in tests. Preserve idempotency keys across retries."
}
```

## 2. A later test-writing skill receives that memory

```bash
python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  pre \
  --skill tdd \
  --task "Add billing retry tests" \
  --file src/billing/retries.ts \
  --cwd /repo/payments
```

Output:

```text
<memanto-engineering-memory>
Apply these prior engineering decisions during this skill run:
- Skill `grill-with-docs` completed task `Review billing retry architecture`. Files in scope: src/billing/retries.ts. Durable engineering memory: Decision: keep retry delays deterministic in tests. Preserve idempotency keys across retries.
</memanto-engineering-memory>
```

## 3. Wrapper mode passes the memory into the command

```bash
python examples/claudecode-skills-memanto/skill_memory.py \
  --backend local \
  --store /tmp/memanto-skills.jsonl \
  wrap \
  --skill handoff \
  --task "Summarize billing retry test constraints" \
  --file src/billing/retries.ts \
  -- python -c "import os; print(os.environ['MEMANTO_SKILL_CONTEXT'])"
```

The wrapped command sees `MEMANTO_SKILL_CONTEXT`, while the wrapper also captures
the command output and stores the completed run back into memory.
