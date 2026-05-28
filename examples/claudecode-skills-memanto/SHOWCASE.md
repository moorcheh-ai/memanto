# Showcase: Claude Code Skills With Shared Memanto Memory

Claude Code skills are sharp, single-purpose workflows. That is useful, but it
also creates context fragmentation: `/grill-with-docs` can discover an
architecture decision that `/tdd` never sees in a later session.

This example adds a tiny Memanto bridge around skill runs:

1. `pre` recalls relevant project memory before a skill starts.
2. `post` distills the completed transcript into durable typed memories.
3. Later skills receive the remembered decisions as prompt-ready constraints.

## Demo Script

Run a planning skill and store its outcome:

```bash
python memanto_skill_memory.py post \
  --skill grill-with-docs \
  --project ./example-saas \
  --summary "Decision: use an outbox table for billing webhooks so retries stay idempotent and auditable."
```

Start a different skill from a fresh shell:

```bash
python memanto_skill_memory.py pre \
  --skill tdd \
  --project ./example-saas \
  --task "Write tests for billing webhook retry behavior"
```

The recalled memory block gives `/tdd` the prior outbox-table decision without
the user repeating it.

## Local Distillation Preview

The sample transcript can be inspected without API credentials:

```bash
python memanto_skill_memory.py demo-distill sample_transcripts/grill_with_docs.md
```

Expected extracted memories:

```text
- decision: Decision: use an outbox table for billing webhook side effects instead of calling downstream services inline.
- instruction: Constraint: every webhook handler must be idempotent by provider event id.
- preference: Preference: keep provider-specific payload parsing in adapter modules and keep domain services provider-agnostic.
- artifact: Artifact: created an ADR draft describing event ingestion, outbox processing, and retry observability.
- learning: Learned: the current codebase already has a job runner, so webhook replay should reuse that queue instead of adding a second worker system.
```

## Social Post Draft

Use this as the public showcase text:

```text
I built a Memanto bridge for Claude Code skills so planning context can survive
across /grill-with-docs, /tdd, /diagnose, and /handoff.

The pre-hook recalls relevant project decisions before a skill starts. The
post-hook distills completed transcripts into typed Memanto memories. That means
a decision found during architecture planning can be injected later into a fresh
TDD session without repeating yourself.

PR: https://github.com/moorcheh-ai/memanto/pull/578
#moorcheh-ai #Memanto #ClaudeCode
```
