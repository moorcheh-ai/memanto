# Memanto Skill Memory Bridge

**Evolving Engineering Profile for Claude Code / mattpocock developer skills.**

## The Problem

mattpocock's skills ecosystem (`/grill-with-docs`, `/tdd`, `/handoff`, `/architect`, etc.) are powerful single-purpose CLI primitives. But every invocation is isolated — the architectural decisions from `/grill-with-docs` vanish when you run `/tdd` in a fresh terminal. You manually re-state your codebase preferences, constraints, and patterns across every session.

## How This Solves It

The **Engineering Profile** is a structured, evolving document of what Memanto has learned about your engineering context. It's built across skill sessions:

```
/grill-with-docs  ──┐
/architect         ─┤
/tdd               ─┼── Memanto ── Engineering Profile
/handoff           ─┤     ▲
/decide            ─┘     │
                    answer() + remember()
```

- **Pre-hook**: Before a skill runs, the profile is searched for relevant engineering context and injected as structured system constraints.
- **Post-hook**: After a skill completes, Memanto's LLM extracts structured insights (via `answer()`) and evolves the profile — classifying them into categories, detecting duplicates, tracking confidence, and marking superseded entries.
- **Profile visualization**: `python bridge.py profile` shows everything Memanto has learned, organized by category with confidence scores.

## Categories

| Category | What it captures | Example |
|----------|-----------------|---------|
| `architecture` | System design, tech stack, component layout | "Hexagonal ports/adapters pattern" |
| `preference` | Developer defaults, tooling choices | "Prefer JWT over sessions" |
| `constraint` | Hard limits, must-haves | "Must support IE11 compatibility" |
| `pattern` | Recurring code patterns | "Use Repository pattern for data access" |
| `decision` | Explicit technical choices | "Use OAuth 2.1 with PKCE flow" |
| `convention` | Team rules, workflow standards | "Conventional Commits format" |

## Quick Start

```bash
# 1. Get a free API key from https://moorcheh.ai
export MOORCHEH_API_KEY="your-key"

# 2. Install memanto
pip install memanto

# 3. Use local mode (no credentials needed for testing)
export MEMANTO_BACKEND=local

# 4. Run skills with memory
python bridge.py wrap /grill-with-docs src/auth.ts "$(cat transcript.txt)"

# 5. See what Memanto has learned
python bridge.py profile
```

## CLI Commands

```
python bridge.py pre       <skill> <target>     # Inject context before a skill
python bridge.py post      <skill> <target> [transcript]  # Store insights after
python bridge.py wrap      <skill> <target> [transcript]  # Full lifecycle
python bridge.py profile                         # View engineering profile
python bridge.py validate                        # Dry-run (no credentials)
python bridge.py benchmark                       # Measure context reuse
```

## Skill → Category Mapping

| Skill | Default Category |
|-------|-----------------|
| `/grill-with-docs`, `/grill-me`, `/decide`, `/board` | `decision` |
| `/architect`, `/design` | `architecture` |
| `/tdd`, `/test` | `pattern` |
| `/handoff`, `/review` | `convention` |
| `/capture`, `/reflect` | `preference` |
| `/freeze`, `/execute` | `constraint` |
| `/plan` | `decision` |
| `/fix` | `pattern` |

## How the Benchmark Works

The benchmark runs 3 skills against the same target (`src/auth.ts`) in sequence:

1. `/grill-with-docs` → No prior context (first run). Extracts and stores: *"Decision: Use OAuth 2.1 with PKCE."*
2. `/tdd` → Finds the OAuth decision from step 1. Extracts: *"Added tests for OAuth edge cases."*
3. `/handoff` → Finds BOTH prior insights. Extracts: *"Auth module complete."*

**Result**: 2 of 2 reducible runs found context = 100% reduction in repeated instructions (in this benchmark scenario).

## Privacy

- All credentials read from environment variables only
- `local` mode stores data in `.jsonl` and `.json` files in your project root
- `live` mode uses your personal Moorcheh namespace
- No secrets committed to git
