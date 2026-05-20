# Claude Code Skills + Memanto Global Memory

This example shows how Memanto can act as a global memory companion across
separate developer skill runs, such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The example is intentionally reviewable without private credentials:

- `local-preview` mode stores memories in a local JSONL file and uses a
  deterministic token-overlap recall strategy.
- `memanto-cli` mode can be enabled when `memanto` is configured with a
  Moorcheh API key in the developer's environment.

## What It Demonstrates

1. A skill starts and asks the memory hook for relevant prior engineering
   decisions.
2. The skill receives a concise context block that can be appended to its
   prompt.
3. When the skill finishes, the hook distills durable engineering memories from
   its transcript.
4. A later skill in a fresh terminal can recall those decisions without manual
   context shoving.

## Files

| File | Purpose |
| --- | --- |
| `skill_memory.py` | Memory store adapters and the reusable skill lifecycle hook. |
| `demo.py` | Two-session demo that simulates separate skill executions. |
| `validate.py` | Credential-free regression check for the demo behavior. |
| `demo-transcript.md` | Expected demo output for quick review. |

## Quick Start

Run the credential-free preview:

```bash
cd examples/claudecode-skills-memanto
python validate.py
python demo.py
```

Use a custom local memory path:

```bash
MEMANTO_SKILLS_MEMORY=.demo-memory/memories.jsonl python demo.py
```

Use a configured Memanto CLI instead of the local preview:

```bash
MEMANTO_SKILLS_BACKEND=memanto-cli python demo.py
```

`memanto-cli` mode expects the repository's normal Memanto CLI setup to already
be complete, including a Moorcheh API key and active agent/session.

## Integration Pattern

Call `before_skill()` at the start of a skill command:

```python
from skill_memory import SkillMemoryHook, build_memory_store

hook = SkillMemoryHook(build_memory_store())
context_block = hook.before_skill(
    skill_name="/tdd",
    task="Add tests for invoice retry scheduling",
    files=["billing/retry.py"],
)
```

Append `context_block` to the skill prompt when it is non-empty.

Call `after_skill()` when the skill finishes:

```python
hook.after_skill(
    skill_name="/grill-with-docs",
    task="Review billing retry architecture",
    transcript=review_transcript,
    files=["billing/retry.py", "docs/billing.md"],
)
```

The hook captures durable memories such as:

- architecture decisions
- framework preferences
- file-specific constraints
- validation commands
- handoff notes

## Review Notes

The local preview exists so reviewers can validate the workflow without secrets
or hosted services. The same lifecycle interface can use Memanto through the CLI
adapter once credentials are configured.

