# Claude Code Skills + Memanto

This example shows how Memanto can act as a shared engineering memory layer
across mattpocock-style skill runs such as `/grill-with-docs`, `/tdd`, and
`/handoff`.

It is designed for safe review:

- The default backend is a local JSONL file, so no private API key is required.
- The live backend uses `memanto.cli.client.sdk_client.SdkClient` only when
  `MEMANTO_MEMORY_BACKEND=sdk` and `MOORCHEH_API_KEY` are configured.
- The hook stores typed engineering memories after a skill finishes, then
  injects relevant memories before later skill runs.

## What This Demonstrates

- **Cross-skill recall**: decisions from one skill run are available to the next.
- **Active extraction**: skill transcripts are distilled into typed memories.
- **Dynamic injection**: relevant memories become a compact context block.
- **Credential-free validation**: tests and demo run locally without network calls.
- **Adapter path**: wrapper generation for common developer skill commands.

## Quick Demo

```bash
cd examples/claudecode-skills-memanto

# Store memories from a completed architecture discussion.
python3 skill_memory.py after \
  --skill grill-with-docs \
  --task "Plan invoice import architecture" \
  --transcript demo_transcript.md \
  --workspace example-shop

# Start a later TDD session and inject relevant context.
python3 skill_memory.py before \
  --skill tdd \
  --task "Write tests for the invoice import parser" \
  --file src/invoices/parser.ts \
  --workspace example-shop
```

Expected output from the second command includes remembered constraints such as:

- prefer a streaming parser for large invoice exports
- keep raw import rows for auditability
- avoid adding a second queue system

Those memories are not passed through the current task prompt. They come from
the previous skill run stored in the shared memory backend.

## Live Memanto Mode

```bash
export MEMANTO_MEMORY_BACKEND=sdk
export MOORCHEH_API_KEY=...
export MEMANTO_AGENT_ID=developer-skills

python3 skill_memory.py after \
  --skill grill-with-docs \
  --task "Plan invoice import architecture" \
  --transcript demo_transcript.md

python3 skill_memory.py before \
  --skill tdd \
  --task "Write tests for the invoice import parser"
```

The SDK backend creates the agent if needed, activates a session, then uses
Memanto `remember` and `recall` operations with typed memory records.

## Generate Skill Wrappers

```bash
python3 mattpocock_adapter.py generate --out .generated-wrappers
```

The generated shell wrappers surround each skill command with:

1. a `before` hook that writes relevant memories into a context file
2. the original skill command
3. an `after` hook that distills the transcript and stores new memories

This keeps the integration outside the skills themselves, so teams can adopt it
incrementally.

## Validation

```bash
python3 validate.py
python3 -m unittest test_skill_memory.py
python3 -m py_compile skill_memory.py mattpocock_adapter.py validate.py test_skill_memory.py
```

These commands do not require credentials or network access.

## File Structure

```text
examples/claudecode-skills-memanto/
├── README.md
├── demo_transcript.md
├── mattpocock_adapter.py
├── skill_memory.py
├── test_skill_memory.py
└── validate.py
```
