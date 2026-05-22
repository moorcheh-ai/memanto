# Memanto + mattpocock/skills for Claude Code

This example connects Memanto to the `mattpocock/skills` workflow by using
Claude Code hooks as a global memory layer.

The goal is to remove repeated instructions across skill runs. A
`/grill-with-docs` session can store architecture choices and domain language;
a later `/tdd`, `/diagnose`, or `/handoff` session receives those memories
automatically before the model starts work.

## What It Adds

- `UserPromptSubmit` and `UserPromptExpansion` recall Memanto memories and inject
  relevant context with `additionalContext`.
- `PostToolUse` records file edits, verification commands, and other important
  tool activity while the skill runs.
- `Stop` distills durable items from the prompt, final response, and tool trail,
  then stores typed Memanto memories such as `decision`, `instruction`,
  `preference`, `artifact`, `learning`, and `error`.
- `PostCompact` preserves Claude Code compact summaries as long-lived context.
- A credential-free local backend lets maintainers run the demo and tests
  without a Moorcheh API key. Set `MEMANTO_SKILLS_BACKEND=cli` for real Memanto
  CLI storage and recall.

## Quickstart

From this repository:

```bash
python examples/claudecode-skills-memanto/install.py --project-dir /path/to/your/project
```

Then in the target project:

```bash
# Optional for live Memanto. Without this, the local JSONL backend is used.
export MEMANTO_SKILLS_BACKEND=cli
export MEMANTO_AGENT_ID=my-project-skills

memanto agent create my-project-skills
```

The installer copies the hook script to `.claude/hooks/` and merges the hook
configuration into `.claude/settings.json`, creating a `.bak` backup if a
settings file already exists.

For review without modifying a project:

```bash
python examples/claudecode-skills-memanto/install.py --dry-run
```

## How the Hook Flow Works

1. A user invokes a skill such as `/grill-with-docs`, `/tdd`, or `/handoff`.
2. The prompt hook detects the skill and expands the recall query with
   skill-specific hints. For `/tdd`, it asks for testing strategy, public API
   decisions, mocking policy, and verification commands.
3. Memanto memories are returned as factual project context through
   `additionalContext`.
4. Tool hooks track files changed and commands run during the skill execution.
5. The stop hook stores durable outcomes back into Memanto with type,
   confidence, provenance, source, and tags.

This keeps the skills small and composable while giving them shared memory.

## Local Demo

Run a prompt hook with the local backend:

```bash
printf '{"session_id":"demo","cwd":"%s","hook_event_name":"UserPromptSubmit","prompt":"/tdd implement webhook tests"}' "$PWD" \
  | python examples/claudecode-skills-memanto/memanto_skill_memory.py --hook UserPromptSubmit --pretty
```

See `demo_transcript.md` for a complete two-session example where
`/grill-with-docs` stores a testing rule and `/tdd` receives it later.

## Verification

```bash
python -m py_compile \
  examples/claudecode-skills-memanto/memanto_skill_memory.py \
  examples/claudecode-skills-memanto/install.py

python -m unittest discover -s examples/claudecode-skills-memanto/tests
```

The tests use only the Python standard library and the local JSONL backend.

## Live Memanto Mode

Set these environment variables before launching Claude Code:

```bash
export MEMANTO_SKILLS_BACKEND=cli
export MEMANTO_AGENT_ID=my-project-skills
```

The bridge activates the configured agent and uses:

- `memanto recall` during prompt hooks
- `memanto remember` during stop, compact, and failure hooks

If the CLI is not available or no API key is configured, the bridge falls back
to `.claude/memanto-skills-state/memories.jsonl` so review never blocks on
private credentials.

## Why This Fits mattpocock/skills

The skills remain sharp, single-purpose command primitives. Memanto provides the
shared layer around them:

- `/grill-with-docs` creates durable decisions and project language.
- `/tdd` receives the relevant testing constraints before writing tests.
- `/diagnose` can recall prior failures and fixes.
- `/handoff` can store and retrieve stable status, commitments, and next steps.

That means fewer repeated instructions and less context fragmentation across
fresh terminals and later sessions.
