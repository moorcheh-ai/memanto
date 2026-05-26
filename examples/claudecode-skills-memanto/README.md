# Claude Code Skills + Memanto Memory Companion

This example shows how a `mattpocock/skills`-style skill pack can use Memanto as persistent, typed memory for coding agents.

The goal is simple:

- Skills keep reusable procedures in versioned files.
- Memanto remembers project facts, decisions, preferences, errors, and lessons across sessions.
- Claude Code or any shell-capable coding agent can call the helper script before and after a task.

This example is safe for reviewers: every command supports `--dry-run`, so it can be tested without a Moorcheh API key or a live Memanto agent.

## Files

```text
examples/claudecode-skills-memanto/
  README.md
  skills/memanto-project-memory/SKILL.md
  scripts/memanto_skill_memory.py
```

## Quick start

```bash
cd examples/claudecode-skills-memanto

# Preview commands without touching Memanto
python scripts/memanto_skill_memory.py setup --agent-id demo-project --dry-run
python scripts/memanto_skill_memory.py remember-decision \
  --title "Use SQLite for local cache" \
  --content "Decision: use SQLite for local cache because it is embedded and easy to inspect." \
  --dry-run
python scripts/memanto_skill_memory.py recall --query "local cache decision" --dry-run
```

When Memanto is configured, remove `--dry-run`:

```bash
memanto agent create demo-project --pattern project
python scripts/memanto_skill_memory.py remember-decision \
  --title "Use SQLite for local cache" \
  --content "Decision: use SQLite for local cache because it is embedded and easy to inspect."
python scripts/memanto_skill_memory.py recall --query "local cache decision"
```

## How an agent should use this skill

1. At task start, recall relevant context:

   ```bash
   python scripts/memanto_skill_memory.py recall --query "current project conventions and recent errors"
   ```

2. During the task, store durable learnings only:

   ```bash
   python scripts/memanto_skill_memory.py remember-decision \
     --title "API pagination style" \
     --content "Decision: API list endpoints use cursor pagination, not offset pagination."
   ```

3. After a tricky bug, store the reusable fix:

   ```bash
   python scripts/memanto_skill_memory.py remember-error \
     --title "pytest import path failure" \
     --content "Error: tests failed with ModuleNotFoundError. Solution: run from repo root or set PYTHONPATH=."
   ```

## What to remember vs. not remember

Good memories:

- Stable project conventions.
- Architecture decisions.
- User/team preferences.
- Reusable debugging lessons.
- Integration gotchas.

Bad memories:

- Temporary task progress.
- Raw logs.
- Secrets or API keys.
- One-off TODOs that will be stale tomorrow.

## Why this fits Memanto

Memanto's typed memory model maps directly to agent skill workflows:

| Skill workflow item | Memanto type |
| --- | --- |
| Project convention | `instruction` or `fact` |
| Architecture choice | `decision` |
| Bug fix lesson | `error` or `learning` |
| User preference | `preference` |
| Delivered artifact | `artifact` |

This keeps skills small and reusable while Memanto provides recallable project context across agent sessions.
