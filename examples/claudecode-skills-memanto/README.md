# Claude Code Skills + Memanto

This example wires Memanto into a command-oriented skills workflow so separate skill runs can share durable engineering context.

It targets workflows such as `/spec`, `/tdd`, `/review`, `/handoff`, or mattpocock-style developer skills where each command may start with fresh context.

## What it demonstrates

- **Global memory before a skill starts**: relevant past decisions are recalled and emitted as a compact context block.
- **Active extraction after a skill ends**: decisions, conventions, preferences, gotchas, and bug fixes from the run summary are saved back to Memanto.
- **Cross-session recall**: a later skill command can recover the same architectural choices without manual re-prompting.
- **Zero extra dependencies**: the hook shells out to the existing `memanto` CLI.

## Files

```text
examples/claudecode-skills-memanto/
├── README.md
├── skill_memory_hook.py
├── demo_transcript.md
└── test_skill_memory_hook.py
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

## Dry-run demo without API keys

Use `--dry-run` to see the exact recall/save operations without touching Memanto:

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py post \
  --skill "/review" \
  --summary "Decision: keep repository ports framework-agnostic. Preference: short review comments. Bugfix: fixed stale cache invalidation." \
  --dry-run
```

## Integration pattern

A skills runner can call this hook in two places:

```text
skill starts  -> hook pre  -> inject MEMANTO_CONTEXT -> execute skill
skill exits   -> summarize -> hook post -> durable Memanto memories
```

That closes the context-fragmentation loop: the human explains an architectural decision once, and future skills recover it automatically.
