# Claude Code Skills + Memanto Decision Trail

This example shows how to use Memanto as a shared memory layer for
command-oriented developer skills such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The important distinction from a simple pre/post wrapper is the **decision
trail tap**: a skill run can record mid-session events while the conversation
is still happening. Those events are distilled into typed engineering memories
and then recalled by later skills, even in a fresh terminal session.

## What It Demonstrates

- **Before-skill recall**: injects a compact `MEMANTO_CONTEXT` block based on
  the skill name, task text, cwd, and touched files.
- **During-skill event capture**: records decisions, constraints, gotchas, and
  file-specific notes as they happen, instead of relying only on a final
  summary.
- **After-skill distillation**: converts transcript and event log entries into
  typed memories with confidence, tags, provenance, and file/module scopes.
- **Credential-free review path**: the local JSONL backend proves the lifecycle
  without requiring a Moorcheh API key.
- **Live Memanto path**: set `MEMANTO_SKILLS_BACKEND=memanto-cli` to call the
  installed `memanto recall` and `memanto remember` commands for real storage.

## Quick Demo

Run the demo from this folder:

```bash
python run_demo.py --reset
```

Expected result:

1. Session A simulates `/grill-with-docs` deciding how Stripe webhook handling
   should work.
2. Session A stores the extracted decision trail.
3. Session B simulates a fresh `/tdd` run for the same module.
4. The `/tdd` run receives a `MEMANTO_CONTEXT` block containing the previous
   Stripe webhook idempotency and locking decisions.

## Validation

```bash
python -m py_compile skill_memory.py run_demo.py
python -m unittest discover -s tests -q
python run_demo.py --reset
```

## Live Memanto Mode

Use the normal Memanto CLI setup first:

```bash
memanto agent create developer-skills
memanto agent activate developer-skills
```

Then run:

```bash
MEMANTO_SKILLS_BACKEND=memanto-cli python run_demo.py --reset
```

In this mode, extracted memories are written through `memanto remember`, and
future context is recalled through `memanto recall`.

## Integration Sketch

Wrap a skill command:

```python
from skill_memory import SkillRun, SkillMemoryBridge, default_backend

bridge = SkillMemoryBridge(default_backend())
run = SkillRun(
    skill="/grill-with-docs",
    task="Design Stripe webhook processing",
    cwd="/repo/payments",
    files=["app/webhooks/stripe.py", "tests/test_stripe_webhooks.py"],
)

context = bridge.before_skill(run)
print(context.as_env_block())

# During the skill:
bridge.tap.record(
    "decision",
    "Use event_id as idempotency key",
    files=["app/webhooks/stripe.py"],
)
bridge.tap.record("constraint", "Do not acknowledge webhook before durable write")

# After the skill:
bridge.after_skill(run, transcript_text)
```

The same interface works with the local backend and the live Memanto CLI
backend.
