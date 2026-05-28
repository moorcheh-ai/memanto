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

## Reddit Showcase Draft

Title:

```text
I built a Memanto bridge so Claude Code skills can remember architecture decisions across sessions
```

Body:

```text
I built a small Memanto bridge for Claude Code skills to fix a workflow problem
I keep running into: context fragmentation.

Skills like /grill-with-docs, /tdd, /diagnose, and /handoff are useful because
they are narrow and focused. The downside is that a decision discovered in one
skill run can disappear when another skill starts in a fresh terminal session.

The bridge adds two lifecycle commands:

- pre: recall relevant Memanto memories before a skill starts
- post: distill a completed transcript into durable memories

For example, a planning skill can store:

"Decision: use an outbox table for billing webhooks so retries stay idempotent
and auditable."

Then a later /tdd run can recall that decision before generating tests, without
the user repeating the architectural context.

The example stores supported Memanto memory types such as decision, instruction,
preference, artifact, and learning. It also includes a dry-run mode and a local
distillation demo that works without API credentials.

PR: https://github.com/moorcheh-ai/memanto/pull/578

I am curious whether people would rather wire this directly into skill runners,
or keep it as an explicit wrapper so memory injection stays visible and
debuggable.
```

## X Thread Draft

```text
1/ I built a small Memanto bridge for Claude Code skills so engineering context can survive across /grill-with-docs, /tdd, /diagnose, and /handoff.

2/ The problem is context fragmentation: one skill can discover an architecture decision, but the next skill starts fresh and never sees it.

3/ The bridge has two lifecycle commands:
- pre: recall relevant Memanto memories before a skill starts
- post: distill a completed transcript into durable typed memories

4/ Example: /grill-with-docs stores "use an outbox table for billing webhooks so retries stay idempotent." A later /tdd run recalls that decision before writing retry tests.

5/ PR: https://github.com/moorcheh-ai/memanto/pull/578
#moorcheh-ai #Memanto #ClaudeCode
```
