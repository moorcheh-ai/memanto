# Claude Code Skills + Memanto Active Memory

This example wires `mattpocock/skills` style commands to Memanto so decisions
from one skill execution become available to later skills in fresh sessions.

The core path is intentionally small:

1. `recall` runs before a skill and emits a `<memanto-engineering-memory>` block.
2. the source skill runs with that block as prior engineering context.
3. `store` runs after the skill and saves durable decisions, preferences,
   constraints, quirks, validation commands, and handoff notes.

## What is different here

Most bridge examples can only scrape obvious `Decision:` lines. This one has a
live Memanto path that calls the repository SDK `answer` primitive to distill a
typed engineering profile from a transcript. The local backend stays
credential-free and deterministic so reviewers can validate behavior without
private Moorcheh credentials.

## Files

| File | Purpose |
| --- | --- |
| `skill_memory_bridge.py` | Recall/store/wrap lifecycle and local/SDK/CLI backends. |
| `mattpocock_adapter.py` | Generates memory-aware wrappers for `/grill-with-docs`, `/tdd`, and `/handoff`. |
| `productivity_benchmark.py` | Three-session benchmark showing reduced repeated instructions. |
| `validate.py` | Credential-free smoke validation. |
| `test_skill_memory_bridge.py` | Stdlib regression tests. |
| `demo-transcript.md` | Expected review transcript. |

## Review Without Credentials

```bash
cd examples/claudecode-skills-memanto
python3 validate.py
python3 -m unittest test_skill_memory_bridge.py
python3 productivity_benchmark.py
```

## Live Memanto Mode

Configure Memanto as usual:

```bash
memanto
memanto agent create claude-code-skills
```

Then run the hooks with the SDK backend:

```bash
python3 skill_memory_bridge.py recall \
  --backend sdk \
  --skill /tdd \
  --task "Add invoice retry tests" \
  --file billing/retry.py
```

Store a completed skill transcript:

```bash
python3 skill_memory_bridge.py store \
  --backend sdk \
  --skill /grill-with-docs \
  --task "Review retry architecture" \
  --file billing/retry.py \
  --transcript-file /tmp/grill-with-docs-transcript.txt
```

The SDK backend uses:

- `SdkClient.recall` for targeted memory injection.
- `SdkClient.remember` for typed memory writeback.
- `SdkClient.answer` for active profile extraction from skill transcripts.

## Generate Skill Wrappers

```bash
python3 mattpocock_adapter.py wrappers --output .claude/commands
```

This writes:

- `.claude/commands/grill-with-docs-memory.md`
- `.claude/commands/tdd-memory.md`
- `.claude/commands/handoff-memory.md`

Each wrapper runs recall before the source skill and store after it.

## Benchmark Signal

`productivity_benchmark.py` simulates:

1. `/grill-with-docs` capturing retry architecture decisions.
2. `/tdd` receiving those decisions without manual reprompting.
3. `/handoff` receiving both architecture and test-handoff context.

The output includes a `manual_reprompting` score so reviewers can inspect the
productivity multiplier rather than judging the integration by description only.
