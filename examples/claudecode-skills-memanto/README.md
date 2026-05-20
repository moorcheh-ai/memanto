# Memanto Skill Memory Bridge

**Cross-skill persistent memory for Claude Code / mattpocock developer skills.**

## The Problem

mattpocock's skills ecosystem gives you sharp, single-purpose CLI primitives (`/grill-with-docs`, `/tdd`, `/handoff`, `/architect`, etc.). But every skill invocation runs in isolation — the architectural decisions you made during `/grill-with-docs` are invisible when you run `/tdd` or `/handoff` in a fresh terminal session. You end up re-stating your preferences, constraints, and codebase quirks manually across every session.

## How This Solves It

The Memanto Skill Memory Bridge provides **pre** and **post** hooks that intercept skill execution:

- **Pre-hook**: Before a skill runs, it queries Memanto for past engineering context relevant to the target file/skill. It uses Memanto's `answer()` API (RAG + LLM synthesis) for high-quality context, falling back to `recall()` for raw semantic search.
- **Post-hook**: After a skill completes, it distills the transcript into structured memory and stores it via Memanto's `remember()` API — saving architectural decisions, coding preferences, and codebase patterns.
- **Skill classifier**: Each mattpocock skill is automatically mapped to the right memory type (e.g., `/grill-with-docs` → `decision`, `/tdd` → `learning`, `/architect` → `goal`).
- **Transcript distiller**: Extracts decisions, patterns, and constraints from raw skill transcripts, filtering noise.

## Quick Start

```bash
# 1. Get a free API key from https://moorcheh.ai
export MOORCHEH_API_KEY="your-key-here"

# 2. Install memanto
pip install memanto

# 3. Run the hooked skill
python examples/claudecode-skills-memanto/skill_memory.py wrap /grill-with-docs src/auth.ts "$(cat transcript.txt)"
```

## CLI Commands

```
# Pre-execution: query memory before a skill
python skill_memory.py pre  "/grill-with-docs" "src/auth.ts"

# Post-execution: store context after a skill
python skill_memory.py post "/grill-with-docs" "src/auth.ts" "[transcript content]"

# Full wrap: pre + execution + post
python skill_memory.py wrap "/tdd" "src/auth.ts" "[transcript content]"

# Dry-run validation (no credentials needed)
python skill_memory.py validate
```

## Architecture

```
                    ┌──────────────────────┐
                    │   Claude Code Skill  │
                    │  /grill-with-docs    │
                    │  /tdd /handoff etc.  │
                    └──────┬───────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
        pre_hook()                post_hook()
              │                         │
              ▼                         ▼
    ┌─────────────────┐     ┌─────────────────────┐
    │ Memanto.answer()│     │ Transcript Distiller│
    │ Memanto.recall()│     │         │            │
    └────────┬────────┘     │    Memanto.remember()│
             │              └─────────────────────┘
             ▼
    ┌─────────────────────────────────┐
    │   Injected System Context       │
    │   "User prefers hexagonal arch, │
    │    OAuth 2.1 with PKCE flow."   │
    └─────────────────────────────────┘
```

## Skill → Memory Type Mapping

| Skill | Memory Type | Tag |
|-------|------------|-----|
| `/grill-with-docs`, `/review`, `/challenge`, `/decide` | `decision` | `architecture-review` |
| `/tdd`, `/test`, `/fix` | `learning` | `test-driven-dev` |
| `/handoff`, `/freeze` | `instruction` | `session-handoff` |
| `/architect`, `/design`, `/plan` | `goal` | `system-design` |
| `/capture` | `context` | `brain-dump` |
| `/reflect` | `observation` | — |
| `/execute` | `commitment` | — |

## Privacy

- Credentials are read from environment variables only; never committed
- `validate` mode works without any API key for reviewer testing
- All memory operations use your personal Moorcheh namespace
