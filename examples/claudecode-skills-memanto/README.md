# Claude Code Skills + Memanto Memory Bridge

This example shows how Memanto acts as a **global, active memory companion**
across separate `mattpocock/skills` executions, eliminating repeated context
instructions.

## How it works

```
  Skill A runs  -->  distill()  -->  Memanto stores decisions
       |
       v
  Skill B runs  <--  recall()   <--  Memanto injects prior decisions
```

Instead of treating each terminal command as an isolated event, Memanto
listens to skill inputs/outputs, distills durable engineering decisions,
and injects them into subsequent skill prompts automatically.

## Quick start

### 1. Install Memanto

```bash
pip install memanto
```

### 2. Configure your Moorcheh API key

```bash
memanto  # interactive setup, or set MOORCHEH_API_KEY
```

### 3. Use the hook

**Before a skill runs:**

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py recall \
  --skill tdd \
  --task "Add invoice retry policy" \
  --file src/billing/retries.ts
```

This prints a `<memanto-engineering-memory>` block and sets
`MEMANTO_SKILL_CONTEXT` for child processes.

**After a skill completes:**

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py store \
  --skill tdd \
  --task "Add invoice retry policy" \
  --file src/billing/retries.ts \
  --transcript-file /tmp/skill-output.txt
```

**Full lifecycle wrapper:**

```bash
python examples/claudecode-skills-memanto/skill_memory_hook.py wrap \
  --skill tdd \
  --task "Add invoice retry policy" \
  --file src/billing/retries.ts \
  -- python -m pytest tests/test_retries.py
```

## Backends

| Mode | Flag | Requires API key? | Use case |
|------|------|-------------------|----------|
| `local` | `--backend local` | No | Reviewer validation, demos |
| `sdk` | `--backend sdk` | Yes | Production — direct Python SDK |
| `cli` | `--backend cli` | Yes | Fallback — shells out to `memanto` CLI |

### Credential-free preview

Reviewers can validate the entire lifecycle without a Moorcheh API key:

```bash
python examples/claudecode-skills-memanto/validate.py
```

### Live mode with SDK

```bash
export MOORCHEH_API_KEY=your-key
export MEMANTO_SKILLS_BACKEND=sdk
python examples/claudecode-skills-memanto/skill_memory_hook.py recall --skill tdd --task "..."
```

## mattpocock/skills adapter

Generate Claude Code command wrappers for the three skills named in the bounty:

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py wrappers
```

This creates `.claude/commands/grill-with-docs-memory.md`, `tdd-memory.md`,
and `handoff-memory.md` — each with built-in recall/store hooks.

Print a JSON spec for one skill:

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py spec tdd --task "Implement X"
```

## What gets remembered

The distiller extracts durable engineering signals:

| Pattern | Memory type | Confidence |
|---------|-------------|------------|
| `Decision: ...`, `we will ...` | `decision` | 0.85 |
| `Preference: ...`, `convention ...` | `preference` | 0.75 |
| `Must: ...`, `Never ...`, `Always ...` | `instruction` | 0.90 |
| `Quirk: ...`, `Caveat: ...` | `context` | 0.65 |
| `Trade-off: ...` | `context` | 0.70 |
| `Follow-up: ...`, `TODO: ...` | `context` | 0.60 |

Each memory is tagged with the skill name and touched files for targeted recall.

## Environment variable injection

The `recall` command sets `MEMANTO_SKILL_CONTEXT` so child processes can read
the context without parsing stdout:

```bash
python skill_memory_hook.py recall --skill tdd --task "..."
echo "$MEMANTO_SKILL_CONTEXT"
```

## Files

| File | Purpose |
|------|---------|
| `skill_memory_hook.py` | Core lifecycle: recall, store, wrap |
| `mattpocock_adapter.py` | Generates Claude command wrappers + JSON specs |
| `validate.py` | Credential-free smoke test |
| `test_skill_memory_hook.py` | Comprehensive pytest test suite |
| `demo-transcript.md` | Two-session walkthrough |

## Verification

```bash
# Credential-free validation
python examples/claudecode-skills-memanto/validate.py

# Full test suite
cd examples/claudecode-skills-memanto
python -m pytest test_skill_memory_hook.py -v

# Syntax check
python -m py_compile skill_memory_hook.py mattpocock_adapter.py validate.py
```

## Architecture

```
                    ┌─────────────────┐
                    │   Skill Runner   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ recall() │  │  run cmd │  │ store()  │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │              │              │
             ▼              ▼              ▼
        ┌─────────────────────────────────────┐
        │          MemoryBackend               │
        │  ┌──────┐  ┌─────┐  ┌────────────┐  │
        │  │local │  │ sdk │  │   cli      │  │
        │  │JSONL │  │client│  │ subprocess │  │
        │  └──────┘  └─────┘  └────────────┘  │
        └─────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Memanto API    │
                    │  (or local file) │
                    └─────────────────┘
```
