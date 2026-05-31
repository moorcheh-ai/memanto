# Claude Code Skills + Memanto

This example shows how Memanto can act as a cross-session memory layer for
command-oriented developer skills such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The important part is the **decision trail tap**. A start/end hook can only see
the prompt and final summary; many durable engineering choices happen between
tool calls. This example records those mid-session decisions, constraints,
preferences, and gotchas, then injects the relevant memories into a later skill
run as a compact `MEMANTO_CONTEXT` block.

## What It Demonstrates

- Before a skill starts, `SkillMemoryBridge.begin_skill()` recalls project,
  file, and task-relevant memories.
- During a skill, `record_event()` captures mid-session decisions and
  constraints with file provenance.
- After a skill, `end_skill()` persists typed memories plus a completion
  summary.
- Later skills receive the remembered engineering context without repeated
  prompting.
- Reviewers can run everything locally without a Moorcheh API key.

## Run The Demo

```bash
cd examples/claudecode-skills-memanto
python demo.py
```

Expected behavior:

1. The first `/grill-with-docs` run starts with no recalled memory.
2. It records a payment retry decision, a non-retry constraint, and a test
   gotcha.
3. A later `/tdd` run receives a `MEMANTO_CONTEXT` block containing those
   decisions.

## Run Tests

```bash
python -m pytest examples/claudecode-skills-memanto -q
```

## Live Memanto Mode

The local JSONL backend is only for deterministic review. To use the installed
Memanto CLI instead:

```python
from skill_memory_bridge import MemantoCliBackend, SkillMemoryBridge

bridge = SkillMemoryBridge(
    MemantoCliBackend(),
    project_slug="checkout-service",
)
```

Activate an agent first:

```bash
memanto agent activate checkout-service
```

The adapter never handles API keys directly. It delegates credentials and active
session state to the existing `memanto` CLI.

## Why This Is Different From A Start/End Wrapper

Boundary-only hooks are clean, but they miss the decision path:

- a branch discarded after a failed tool run,
- a constraint discovered while editing a file,
- a style preference agreed during review,
- a test gotcha that only appears in intermediate output.

The event tap stores those moments as first-class memories. Retrieval can then
key off the current task, file path, and skill name so a future `/tdd` run can
see architectural choices made during a previous `/grill-with-docs` session.
