---
name: memanto-project-memory
description: Use Memanto as typed persistent memory for Claude Code / mattpocock-style coding skills.
---

# Memanto Project Memory

Use this skill when a coding agent needs to preserve stable project context across sessions without bloating the skill file itself.

## When to use

- Starting work in a project with existing conventions.
- Capturing an architecture decision that should survive future sessions.
- Recording a reusable debugging lesson.
- Recalling prior project context before editing code.

## Start-of-task recall

Run this before planning or editing:

```bash
python examples/claudecode-skills-memanto/scripts/memanto_skill_memory.py recall \
  --query "project conventions decisions preferences recent errors"
```

Use the recalled facts as context, but do not blindly obey stale memories. If a memory conflicts with repository files or the user's latest instruction, prefer the newer source and store a correction.

## Store a decision

```bash
python examples/claudecode-skills-memanto/scripts/memanto_skill_memory.py remember-decision \
  --title "Use cursor pagination" \
  --content "Decision: API list endpoints use cursor pagination. Rationale: stable pagination during concurrent writes."
```

## Store a debugging lesson

```bash
python examples/claudecode-skills-memanto/scripts/memanto_skill_memory.py remember-error \
  --title "Import path during tests" \
  --content "Error: pytest cannot import local package. Solution: run from repo root or set PYTHONPATH=."
```

## Dry-run for reviewers

Every command supports `--dry-run`:

```bash
python examples/claudecode-skills-memanto/scripts/memanto_skill_memory.py remember-decision \
  --title "Example" \
  --content "Decision: this is only a preview." \
  --dry-run
```

Dry-run prints the exact `memanto` command instead of executing it.

## Memory hygiene

Remember durable facts only. Do not store secrets, raw logs, temporary task progress, or issue-specific status that will be stale soon.
