# Claude Code Skills + Memanto Memory Integration

Memanto-powered cross-session memory for Claude Code skills (`.claude/commands/*.md`).

## Problem

Each Claude Code skill (`/grill-with-docs`, `/tdd`, `/handoff`) runs in isolation.
Architectural decisions made during one skill execution are invisible when you
invoke another.

## Solution

This integration wraps skill execution with Memanto's semantic memory layer:

1. **Dynamic Injection**: Before a skill runs, queries Memanto for past
   engineering decisions relevant to this repo/skill combo.
2. **Active Extraction**: After a skill completes, stores the interaction summary
   + key decisions in Memanto for future recall.
3. **Zero Repeated Instructions**: Your coding preferences, architectural
   patterns, and codebase quirks persist across sessions.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Moorcheh API key (free at https://moorcheh.ai)
export MOORCHEH_API_KEY="your-key-here"

# Run a skill with Memanto memory
python memory_skills_integration.py /grill-with-docs --repo-dir /path/to/project

# Retrieve existing context only (no execution)
python memory_skills_integration.py /grill-with-docs --context-only
```

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Skill Start │ ──▶ │ Query Memanto│ ──▶ │ Inject      │
│  (/grill-…)  │     │ (similarity) │     │ Context     │
└─────────────┘     └──────────────┘     └─────────────┘
                                                 │
                                                 ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Skill End   │ ◀── │ Store Result │ ◀── │ Execute     │
│  (summary)   │     │ in Memanto   │     │ Skill       │
└─────────────┘     └──────────────┘     └─────────────┘
```

## Architecture

- **MoorchehClient** (`moorcheh-sdk`): Python SDK for Memanto's semantic vector DB
- **Namespace**: `skills-memory` — shared namespace across all skill invocations
- **Query Strategy**: Searches by `{repo} + {skill} + {engineering keywords}`
- **Storage Format**: JSON documents with skill name, repo, summary, metadata

## Testing

```bash
# Run tests
python -m pytest tests/ -v
```

## API Key

Get a free Moorcheh API key at https://moorcheh.ai.
