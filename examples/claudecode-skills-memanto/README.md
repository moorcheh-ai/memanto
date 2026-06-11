# Claude Code Skills + Memanto Example

This example adds a lightweight Memanto memory layer around Claude Code slash-command skills such as `/grill-with-docs`, `/tdd`, and `/handoff` from the `mattpocock/skills` style workflow.

The goal is to remove repeated engineering context between skills and terminal sessions. Before a skill runs, the hook recalls relevant Memanto memories and injects them as extra prompt context. After the run finishes, the hook reads the Claude Code transcript, extracts durable engineering signals, and stores a compact interaction summary back into Memanto.

## What This Demonstrates

- **Global memory hook**: Claude Code hooks call `scripts/memanto_skill_hook.py` during `UserPromptSubmit` and `Stop`.
- **Dynamic injection**: skill prompts receive relevant prior decisions, preferences, constraints, and lessons from `memanto recall`.
- **Active extraction**: completed skill transcripts are summarized into Memanto with `memanto remember` so later skills can reuse the context.
- **Zero hard dependency in the hot path**: if Memanto is not installed, not configured, or temporarily unavailable, the hook logs to stderr and lets Claude Code continue.

## Prerequisites

- Python 3.10+
- Claude Code with hooks enabled
- `memanto` installed and configured
- A Moorcheh API key configured through Memanto
- An active Memanto agent/session

```bash
pip install memanto
memanto
memanto agent create developer-skills
memanto agent activate developer-skills
```

If you have not installed the normal Claude Code Memanto integration yet, run:

```bash
memanto connect claude-code --local
```

That installs the base Memanto memory skill and permissions. This example adds a narrower lifecycle hook for slash-command skill executions.

## Install The Example Hook

From the repository root:

```bash
mkdir -p .claude
cp examples/claudecode-skills-memanto/.claude/settings.example.json .claude/settings.json
```

If you already have `.claude/settings.json`, merge the `hooks` entries from the example instead of replacing your file.

The settings file wires three lifecycle moments:

```text
SessionStart      -> memanto memory sync --project-dir .
UserPromptSubmit  -> memanto recall, then inject relevant context
Stop              -> read transcript, extract durable signals, remember summary
```

## Usage

Run Claude Code normally and invoke a skill:

```text
/grill-with-docs review the auth middleware against our current API conventions
```

On prompt submission, Claude Code runs:

```bash
python3 examples/claudecode-skills-memanto/scripts/memanto_skill_hook.py pre
```

The hook builds a query from the skill name, current working directory, and user prompt, then runs:

```bash
memanto recall "Claude Code skill grill-with-docs cwd ... review the auth middleware ..." --limit 8
```

The recalled memories are printed as prompt context for the skill to apply.

When the skill run finishes, Claude Code runs:

```bash
python3 examples/claudecode-skills-memanto/scripts/memanto_skill_hook.py post
```

The post hook reads the transcript path supplied by Claude Code, extracts statements about decisions, preferences, architecture, bugs, lessons, and constraints, then stores a durable summary:

```bash
memanto remember "Claude Code skill interaction completed..." \
  --type context \
  --confidence 0.85 \
  --provenance observed \
  --source claude_code_skills \
  --tags claude-code,skills-memanto,grill-with-docs
```

Memanto's memory parsing service can reclassify stored content into more specific types when the content clearly contains decisions, instructions, preferences, learnings, or errors.

## Optional Wrapper Mode

If you want to test the recall step without installing hooks, use the wrapper script:

```bash
examples/claudecode-skills-memanto/scripts/run_skill_with_memanto.sh \
  /tdd add coverage for the billing parser
```

The wrapper recalls relevant memories, passes them to Claude Code with `--append-system-prompt`, and then asks the post hook to store any available summary. Hook mode is preferred because Claude Code supplies the transcript path only during real hook execution.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `MEMANTO_SKILL_LIMIT` | Number of recalled memories to inject. Defaults to `8`. |
| `MEMANTO_SKILL_TIMEOUT` | Timeout in seconds for each Memanto CLI call. Defaults to `30`. |
| `MEMANTO_SKILL_NAME` | Overrides automatic slash-command skill detection. Useful for wrapper scripts. |
| `MEMANTO_SKILL_HOOK_DISABLED` | Set to any non-empty value to bypass the hook. |

## Example Cross-Skill Flow

1. Run `/grill-with-docs` and settle on a design choice: "Use FastAPI dependency injection for auth checks, not decorators."
2. The `Stop` hook stores that decision in Memanto as part of the skill interaction summary.
3. Later, in a fresh terminal, run `/tdd add auth middleware tests`.
4. The `UserPromptSubmit` hook recalls the prior auth decision and injects it before `/tdd` starts, so the test plan follows the existing architecture without another manual reminder.

## File Structure

```text
examples/claudecode-skills-memanto/
├── README.md
├── .claude/
│   └── settings.example.json
└── scripts/
    ├── memanto_skill_hook.py
    └── run_skill_with_memanto.sh
```

## Notes

- The hook intentionally stores concise summaries, not full transcripts.
- The hook uses the active Memanto agent/session. Switch projects or profiles with `memanto agent activate <agent-id>`.
- The default `UserPromptSubmit` matcher targets slash commands. If your skills use another invocation pattern, edit the matcher in `.claude/settings.json`.
