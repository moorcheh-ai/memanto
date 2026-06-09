# Claude Code Skills + Memanto

This example wires Memanto into a command-oriented skills workflow so separate skill runs can share durable engineering context.

It targets workflows such as `/spec`, `/tdd`, `/review`, `/handoff`, or mattpocock-style developer skills where each command may start with fresh context.

## What it demonstrates

- **Global memory before a skill starts**: relevant past decisions are recalled and emitted as a compact context block.
- **Mid-session capture while work is happening**: important decisions can be saved immediately instead of waiting for the final summary.
- **Active extraction after a skill ends**: decisions, conventions, preferences, gotchas, and bug fixes from the run summary are saved back to Memanto.
- **Cross-session recall**: a later skill command can recover the same architectural choices without manual re-prompting.
- **Zero extra dependencies**: the production hook shells out to the existing `memanto` CLI.
- **Credential-free evaluation**: a local JSONL backend and deterministic benchmark let reviewers verify the workflow before configuring an account.

## Files

```text
examples/claudecode-skills-memanto/
|-- README.md
|-- skill_memory_hook.py
|-- productivity_benchmark.py
|-- demo_transcript.md
|-- test_productivity_benchmark.py
`-- test_skill_memory_hook.py
```

## Prerequisites

```bash
pip install memanto
memanto
memanto agent create developer-skills
```

Set the active agent once:

```bash
export MEMANTO_SKILLS_AGENT=developer-skills
```

## Pre-skill recall

Before a skill command starts, ask Memanto for relevant constraints:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py pre \
  --task "/tdd add invoice validation" \
  --files "src/billing/invoice.py,tests/test_invoice.py"
```

The hook prints a `MEMANTO_CONTEXT` block that can be injected into the next skill prompt.

## Post-skill capture

After a skill command finishes, pass a concise summary:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py post \
  --skill "/tdd" \
  --summary "Decision: invoices reject negative totals. Convention: billing tests live next to domain fixtures. Gotcha: legacy imports use Decimal strings."
```

The hook stores each extracted memory with a semantic type and tags it with the originating skill.

## Mid-session capture

Some architectural decisions happen between tool calls, before a skill has a final summary. Capture those as soon as they become stable:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py event \
  --skill "/apply" \
  --type decision \
  --note "Use webhook delivery instead of polling for invoice status updates."
```

The event is saved with the originating skill plus a `mid-session` tag, so a later recall can recover the decision even if the session is interrupted before post-skill capture runs.

## Dry-run demo without API keys

Use `--dry-run` to see the exact recall/save operations without touching Memanto:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py post \
  --skill "/review" \
  --summary "Decision: keep repository ports framework-agnostic. Preference: short review comments. Bugfix: fixed stale cache invalidation." \
  --dry-run
```

## Reproducible productivity benchmark

Run a real two-session persistence flow locally, without credentials:

```bash
python examples/claudecode-skills-memanto/productivity_benchmark.py
```

Expected result:

```json
{
  "saved_memories": 3,
  "candidate_memories": 5,
  "recalled_memories": 3,
  "repeated_instructions": 0
}
```

The first simulated skill session records an architectural decision, a test convention, and a legacy-import gotcha, plus two unrelated decoys. The second session starts with fresh skill context and ranks the three relevant memories above both decoys. Production usage remains on the default `memanto` backend; `--backend local --store <path>` exists only for credential-free evaluation and tests.

## Integration pattern

A skills runner can call this hook in three places:

```text
skill starts  -> hook pre   -> inject MEMANTO_CONTEXT -> execute skill
skill runs    -> hook event -> save stable mid-session decisions
skill exits   -> summarize  -> hook post -> durable Memanto memories
```

That closes the context-fragmentation loop: the human explains an architectural decision once, and future skills recover it automatically.

## Reviewer checklist

- Global recall: `pre` emits a bounded `MEMANTO_CONTEXT` block.
- Mid-session capture: `event` persists stable decisions immediately.
- Active extraction: `post` stores typed, low-noise memories.
- Productivity proof: the benchmark reports zero repeated instructions.
- Code quality: standard-library-only implementation with 11 focused tests.
