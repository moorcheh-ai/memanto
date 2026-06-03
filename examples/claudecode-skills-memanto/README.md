# Claude Code Skills + Memanto

This example shows Memanto acting as a persistent memory layer between
command-oriented Claude Code skills such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

The bridge records useful skill outputs after one run, distills them into typed
engineering memories, and injects relevant context before a later skill starts.
It solves the repeated-context problem without requiring every skill to know
about every previous terminal session.

## What This Demonstrates

- Cross-skill recall: a decision captured after `/grill-with-docs` is injected
  before a later `/tdd` run.
- Cross-session persistence: the default JSONL backend survives separate Python
  processes, matching the shape of a new terminal session.
- Typed engineering memories: decisions, conventions, preferences, errors, and
  path anchors are stored separately so future prompts receive concise context.
- Reviewer-safe execution: the default path uses only the Python standard
  library and does not require API keys.
- Live Memanto path: set `MEMANTO_SKILLS_BACKEND=cli` to route the same lifecycle
  calls through the installed `memanto` CLI.

## Quick Start

From this directory:

```bash
python demo.py
python validate.py
python -m unittest test_skill_memory_bridge.py
```

The demo simulates two separate skill sessions:

1. `/grill-with-docs` stores architectural decisions for a Next.js + SQLite SaaS
   codebase.
2. `/tdd` starts later with a different prompt and receives a `MEMANTO_CONTEXT`
   block containing the remembered migration, auth, and database rules.

## CLI Usage

Capture context before a skill starts:

```bash
python skill_memory_bridge.py before \
  --skill /tdd \
  --cwd apps/acme-saas \
  --paths src/app/billing/actions.ts,db/migrations \
  --prompt "Write tests for billing plan changes"
```

Store memories after a skill completes:

```bash
python skill_memory_bridge.py after \
  --skill /grill-with-docs \
  --cwd apps/acme-saas \
  --paths src/app/billing/actions.ts,db/migrations \
  --summary "Decision: Billing mutations stay in server actions.
Convention: SQLite migrations are append-only.
Gotcha: Do not introduce Prisma; use better-sqlite3 helpers."
```

Wrap any command and capture its output:

```bash
python skill_memory_bridge.py wrap \
  --skill /handoff \
  --prompt "Run validation and remember follow-up constraints" \
  -- python validate.py
```

## Live Memanto Backend

The local backend is intentional for tests and pull-request review. To use the
same bridge with real Memanto storage:

```bash
pip install memanto
memanto agent create claudecode-skills
set MEMANTO_SKILLS_BACKEND=cli
python skill_memory_bridge.py before --skill /tdd --prompt "Recall project rules"
```

On macOS/Linux, use `export MEMANTO_SKILLS_BACKEND=cli` instead of `set`.

## Integration Pattern

The example is intentionally small enough to embed in a skill runner:

```python
from skill_memory_bridge import SkillMemoryBridge, create_backend

bridge = SkillMemoryBridge(create_backend())

context = bridge.before_skill(
    skill_name="/tdd",
    prompt="Add regression tests for invoice totals",
    cwd="apps/acme-saas",
    paths=["src/features/invoices"],
)

prompt_for_skill = f"{context}\n\nUSER_TASK:\nAdd regression tests."

bridge.after_skill(
    skill_name="/tdd",
    summary="""
Decision: Invoice totals are stored in cents.
Convention: Tests for invoices live next to the feature folder.
""",
    cwd="apps/acme-saas",
    paths=["src/features/invoices"],
)
```

## Why It Fits the Bounty

Issue #508 asks for a lightweight utility hook in the skills lifecycle that:

- initializes Memanto or a compatible backend,
- listens to important skill inputs and outputs,
- distills architectural choices and coding preferences,
- injects relevant memories into later skill prompts.

This folder implements those hooks as `before_skill`, `after_skill`, and `wrap`
commands. The local JSONL backend keeps review deterministic; the CLI backend
shows the same lifecycle against real Memanto agent memory.

## Validation Notes

The validation suite covers:

- cross-session recall from one bridge instance to another,
- malformed local memory rows being ignored instead of crashing recall,
- extraction of typed memories from skill summaries,
- path-tagged recall so memories follow the files they affect.
