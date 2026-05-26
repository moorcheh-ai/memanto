# Claude Code Skills + Memanto Engineering Memory

This integration gives [mattpocock/skills](https://github.com/mattpocock/skills) persistent engineering memory across terminal sessions using [Memanto](https://memanto.ai/).

## Problem

The `mattpocock/skills` ecosystem provides sharp CLI primitives (`/grill-with-docs`, `/tdd`, `/handoff`) but each execution starts with a blank context. Decisions made during one skill run are invisible to subsequent runs in different sessions.

## Solution

A pre/post skill hook that wraps any skill execution:

```
Normal:      skill run → [no memory] → result
With Memanto: skill run → [recall past decisions] → result → [store new decisions]
```

### Integration files

| File | Purpose |
|------|---------|
| `memanto_skills_hook.py` | Pre/post hook: recalls context before a skill, stores decisions after |
| `pyproject.toml` | Package entry point so `memanto-skills` is available as a CLI command |

## Quick Start

### Prerequisites

1. Memanto installed: `pip install memanto`
2. [Moorcheh API key](https://moorcheh.ai/) configured via `memanto setup`
3. An active Memanto agent: `memanto agent create claude-code-skills`
4. Node.js (for running Claude Code skills)

### Setup

```bash
# Set environment variables (or add to ~/.zshrc)
export MEMANTO_AGENT_ID=claude-code-skills
export MEMANTO_SKILLS_NS=claude-code-skills

# Install the hook as a CLI tool
pip install -e .
```

### Usage

```bash
# Pre-hook: recall context before a skill
memanto-skills pre grill-with-docs

# Post-hook: store decisions after a skill
cat transcript.txt | memanto-skills post grill-with-docs

# Full run: pre + skill + post in one command
memanto-skills run grill-with-docs -- --file src/main.py
```

### Example

```bash
# First run — no context yet
memanto-skills run grill-with-docs -- --file src/main.py
# Output: "# No relevant engineering context found."
#         (executes skill normally)

# Second run — previous decisions are recalled
memanto-skills run grill-with-docs -- --file src/main.py
# Output: "--- Memanto Context for 'grill-with-docs' ---"
#         (includes decisions from first run)
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    memanto-skills                    │
│                                                      │
│  pre(skill_name)                                     │
│    ├─ Query Memanto: "decisions related to {skill}"  │
│    └─ Print compact context block                    │
│                                                      │
│  run(skill_name, args)                               │
│    ├─ pre(skill_name)        ← recall context        │
│    ├─ exec skill_name args   ← execute the skill     │
│    └─ post(skill_name, out)  ← store new decisions   │
│                                                      │
│  post(skill_name, transcript)                        │
│    └─ Store summary in Memanto                       │
└─────────────────────────────────────────────────────┘
```

## How it works

### Pre-hook (`memanto-skills pre <skill>`)

1. Calls `memanto memory export` with a `--query` parameter specific to the skill name
2. Retrieves stored engineering decisions related to that skill
3. Formats them as a compact context block
4. Prints to stdout for piping into the skill prompt

### Post-hook (`memanto-skills post <skill>`)

1. Reads the skill transcript from stdin
2. Writes a summary to a temp file
3. Calls `memanto memory import` to persist the decision summary as a typed memory
4. Future pre-hooks will recall this decision

### Full run (`memanto-skills run <skill> -- <args>`)

1. Pre-hook: recall relevant context (with API key check)
2. Execute the skill with original arguments
3. Post-hook: store new decisions

## Customization

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `MEMANTO_AGENT_ID` | `claude-code-skills` | Memanto agent to use |
| `MEMANTO_SKILLS_NS` | `claude-code-skills` | Namespace for skill memories |
| `MEMANTO_CONTEXT_LIMIT` | `3000` | Max context length to inject |

## Verification

```bash
# Test pre-hook works (no API key needed for help)
memanto-skills

# With Memanto configured, verify context recall
memanto-skills pre tdd
```
