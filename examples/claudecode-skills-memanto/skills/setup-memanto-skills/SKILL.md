---
name: setup-memanto-skills
description: One-time setup that injects a universal Memanto memory hook into CLAUDE.md/AGENTS.md so that ALL skills automatically recall your engineering profile before running and store new insights after. Run once per repo before using any skill. Replaces the need for memory-specific skill variants.
disable-model-invocation: true
---

# Setup Memanto Skills — Universal Memory Hook

Inject a single `## Memanto Memory` block into your repo's `CLAUDE.md` or `AGENTS.md` so that **every skill** — `/tdd`, `/grill-with-docs`, `/diagnose`, `/handoff`, and any future skills — automatically has access to your persistent engineering profile.

This is a one-time setup. No per-skill wrappers. No manual recall commands.

## Prerequisites

`memanto-skills` must be installed and `MOORCHEH_API_KEY` must be set:

```bash
pip install memanto-skills
export MOORCHEH_API_KEY=your_key_here
```

Or add to `.env` in your project root.

## Process

### 1. Explore

Check which config file exists:

- If `CLAUDE.md` exists at the repo root → edit it
- Else if `AGENTS.md` exists → edit it
- If neither exists → create `CLAUDE.md`

Check if a `## Memanto Memory` block already exists. If it does, update in-place rather than duplicating.

### 2. Inject the universal hook

Add the following block to the file. Place it near the top, before any skill-specific sections:

```markdown
## Memanto Memory

Before running ANY skill, always execute:

```bash
memanto-skills recall <skill-name> --hint "<brief task description>"
```

Read the output carefully. It contains your persistent engineering profile:
- `[instruction]` entries are **hard rules** — always follow them
- `[decision]` entries are **past choices** — do not re-litigate them
- `[preference]` entries are **style choices** — honour them

After completing ANY skill, ask: "Should I save anything from this session?"
If yes, run:

```bash
memanto-skills store <skill-name> "<insight>" --type <type>
```

Where `<type>` is one of: `instruction`, `decision`, `preference`, `learning`, `fact`, `artifact`, `goal`.

You have access to the following `memanto-skills` commands:
- `memanto-skills recall <skill> [--hint TEXT]` — retrieve relevant memories
- `memanto-skills store <skill> <summary> [--type TYPE]` — persist an insight  
- `memanto-skills profile` — view full engineering profile
- `memanto-skills store-file <skill> <path>` — store contents of a file as memories
```

### 3. Confirm and write

Show the user the diff before writing. Confirm the location of the block in the file.

### 4. Done

Tell the user:
- The hook is now active for ALL skills in this repo
- No per-skill configuration needed
- Run `/memanto-recall` at any time to see the current engineering profile
- Run `memanto-skills profile` in the terminal to inspect stored memories
- The more they use skills and store insights, the more context gets injected automatically
