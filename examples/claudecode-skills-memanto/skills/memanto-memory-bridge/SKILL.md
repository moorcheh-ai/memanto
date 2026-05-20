# Memanto Memory Bridge

Use this skill glue when a Claude Code skill should inherit remembered
engineering context from previous skill runs.

## Before Running Another Skill

Run:

```bash
python examples/claudecode-skills-memanto/skill_memory.py before \
  --skill "$TARGET_SKILL" \
  --task "$TASK_SUMMARY" \
  --paths "$PRIMARY_PATH"
```

Then include `.memanto-skill-memory/injected-context.md` in the next prompt.
Treat it as constraints, not as proof. If the current code contradicts memory,
prefer current code and store the correction after the run.

## After The Skill Finishes

Save the useful terminal/session summary to a transcript file, then run:

```bash
python examples/claudecode-skills-memanto/skill_memory.py after \
  --skill "$TARGET_SKILL" \
  --task "$TASK_SUMMARY" \
  --paths "$PRIMARY_PATH" \
  --transcript .memanto-skill-memory/session.md
```

The bridge stores durable decisions, preferences, instructions, and codebase
quirks so later skills do not need the same manual context again.

## Live Memanto Mode

Preview mode is the default. To use Memanto:

```bash
export MOORCHEH_API_KEY=...
export MEMANTO_LIVE=1
```

Live mode uses the installed `memanto` CLI and the `claude-code-skills` agent
namespace by default.
