# Claude Code Skills + Memanto Memory Bridge

This example shows a lightweight integration layer for using Memanto as active
memory between separate Claude Code skill runs.

The bridge has two modes:

- **Preview mode** works without credentials and stores memories in local JSONL.
- **Live mode** uses the Memanto CLI when `MOORCHEH_API_KEY` is configured.

## Three-step setup

1. Install Memanto and configure your Moorcheh key:

   ```bash
   pip install memanto
   memanto
   ```

2. Copy this folder into a repo that uses Claude Code skills.

3. Wrap each skill call:

   ```bash
   python examples/claudecode-skills-memanto/skill_memory.py before \
     --skill grill-with-docs \
     --task "Review the API client retry strategy" \
     --paths "src/api/client.ts"

   # Run the skill and save its transcript, then:
   python examples/claudecode-skills-memanto/skill_memory.py after \
     --skill grill-with-docs \
     --task "Review the API client retry strategy" \
     --transcript .memanto-skill-memory/session.md
   ```

The `before` command writes a concise context block to
`.memanto-skill-memory/injected-context.md`. Paste or include that block in the
next skill prompt so later skills inherit relevant architectural decisions.

For a full lifecycle wrapper, put the target command after `--`:

```bash
python examples/claudecode-skills-memanto/skill_memory.py wrap \
  --skill tdd \
  --task "Implement API client retry handling" \
  --paths "src/api/client.ts" \
  -- python -c "print('Decision: keep retries in the transport adapter')"
```

The wrapper recalls memory, runs the command, captures the transcript, and
stores durable decisions from the result.

To generate command wrappers for the common `mattpocock/skills` commands:

```bash
python examples/claudecode-skills-memanto/mattpocock_adapter.py \
  --output .claude/commands
```

This creates reviewable command files such as `grill-with-docs-memory.md`,
`tdd-memory.md`, and `handoff-memory.md`. Each wrapper tells the agent to recall
Memanto context before invoking the source skill and store durable decisions
after it completes.

## What it captures

The bridge looks for durable engineering signals such as:

- explicit decisions,
- "must" and "prefer" constraints,
- codebase quirks,
- accepted tradeoffs,
- follow-up tasks.

In live mode, those memories are sent to Memanto as typed `decision`,
`preference`, `instruction`, or `context` records. In preview mode, the same
records are written locally so reviewers can inspect behavior without private
credentials.

## Files

- `skill_memory.py` - before/after hook wrapper.
- `mattpocock_adapter.py` - generates Claude command wrappers for common
  `mattpocock/skills` workflows.
- `validate.py` - credential-free smoke test for reviewers.
- `skills/memanto-memory-bridge/SKILL.md` - Claude Code skill glue.
- `demo/demo-transcript.md` - sample two-skill walkthrough.
- `sample-output/injected-context.md` - example injected memory block.

## Review-safe behavior

The default command path does not require API keys, network calls, package
installation, or access to private code. Set `MEMANTO_LIVE=1` only when you want
the hook to call the installed Memanto CLI.
