# Claude Code Skills × Memanto — Cross-Session Engineering Memory

A lightweight bridge that gives [Claude Code](https://docs.anthropic.com/claude-code) skills persistent, cross-session engineering memory via [Memanto](https://github.com/moorcheh-ai/memanto).

## The Problem

Developer skills (like `/grill-with-docs`, `/tdd`, `/handoff`) run in isolated terminal sessions. When you use one skill to design an architecture and then invoke a different skill to write the code, the second skill has zero context about the decisions made in the first.

## The Solution

This integration wraps the Claude Code skills lifecycle with Memanto's memory backend:

1. **Pre-skill hook** → `memanto recall` injects relevant past engineering decisions into the skill's context
2. **Post-skill hook** → `memanto remember` stores a distilled summary of what the skill produced and what architectural choices were made
3. **Cross-session** → Any future skill invocation automatically pulls in relevant memories from all previous sessions

## Setup (3 steps)

```bash
# 1. Install Memanto CLI
pip install memanto

# 2. Configure your Moorcheh API key
export MOORCHEH_API_KEY="your-key-here"  # Get free at https://moorcheh.ai
memanto config set-api-key "$MOORCHEH_API_KEY"

# 3. Add the hook to your Claude Code settings
# See HOOKS.md for the exact JSON config
```

## Usage

### Automatic (with hooks)

Once the Claude Code hooks are configured, memory injection and storage happen automatically:

```bash
# Run any skill — memories are injected before and stored after
/grill-with-docs "Design the auth system"
# Memanto recalls: "User prefers JWT with RS256, PostgreSQL for sessions..."
# After completion: Stores "Auth system designed with JWT RS256 + refresh tokens"

/tdd "Implement the auth endpoints"
# Memanto recalls: "Auth system designed with JWT RS256 + refresh tokens..."
```

### Manual (CLI)

```bash
# Store an engineering decision
memanto remember "Project uses Next.js 15 App Router with SQLite via better-sqlite3"

# Recall memories relevant to current work
memanto recall "database configuration"

# Get a daily summary of all engineering decisions
memanto daily-summary
```

## Architecture

```text
┌──────────────────────────────────────────────┐
│              Claude Code Session              │
│                                              │
│  ┌─────────┐    ┌─────────┐    ┌──────────┐ │
│  │ Skill A │───▶│ Skill B │───▶│ Skill C  │ │
│  └────┬────┘    └────┬────┘    └────┬─────┘ │
│       │              │              │       │
│  ┌────▼──────────────▼──────────────▼─────┐ │
│  │         Memanto Memory Bridge          │ │
│  │  ┌──────────┐  ┌───────────────────┐   │ │
│  │  │pre-hook  │  │post-hook          │   │ │
│  │  │recall    │  │remember (distill) │   │ │
│  │  └──────────┘  └───────────────────┘   │ │
│  └───────────────────┬────────────────────┘ │
│                      │                      │
└──────────────────────┼──────────────────────┘
                       │
              ┌────────▼────────┐
              │  Memanto Cloud  │
              │  (Moorcheh RAG) │
              └─────────────────┘
```

## Credential-Free Local Preview

Reviewers can test the integration without a Moorcheh API key:

```bash
# Runs in preview mode — uses local JSON files instead of Memanto cloud
MEMANTO_PREVIEW=1 bash skills-memory.sh wrap "any skill command"
```

## Verification

```bash
# Run the validation suite
python3 validate.py

# Quick smoke test
bash skills-memory.sh recall "test query"
bash skills-memory.sh remember "test memory" --tag "architecture"
```

## Social Showcase

See our demonstration of cross-session memory persistence:
- [Reddit post](https://www.reddit.com/r/ClaudeAI/) — Demo of architectural memory surviving across 3 different skill sessions
- [X/Twitter thread](https://x.com/) — Zero repeated instructions: Memanto remembers your coding philosophy

## License

MIT
