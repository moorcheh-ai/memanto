# Claude Code Skills × Memanto — Persistent Developer Memory

> **Zero context re-prompting.** Engineering preferences captured once, recalled automatically across every Claude Code session.

This example integrates **Memanto** into Claude Code's hook lifecycle so that your architectural decisions, tool preferences, and coding patterns are automatically captured at the end of each session and injected as context at the start of the next — eliminating the need to re-explain your project's conventions to Claude every single time.

## The Problem

Every time you start a new Claude Code session you have to re-explain:
- "We use FastAPI, not Flask"
- "httpx is our HTTP client, not requests"
- "PostgreSQL on prod, SQLite only for local dev"
- "All tests must be in tests/ with ≥80% coverage"

After the fifth session this becomes friction. After the fiftieth it's a tax on every engineer on the team.

## The Solution

Two lightweight Claude Code hooks wired to Memanto:

| Hook | Event | What it does |
|------|-------|-------------|
| `capture_preferences.py` | `Stop` | Scans the session transcript for preference/decision signals → stores in Memanto |
| `inject_context.py` | `UserPromptSubmit` | Queries Memanto with the user's first message → injects relevant memories as `additionalSystemPrompt` |

Memories are scoped to the project directory (deterministic namespace from `md5(cwd)`), so each project has its own isolated memory pool.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code CLI                    │
│                                                      │
│  User types: "Add a new API endpoint"               │
│       │                                              │
│       ▼  UserPromptSubmit hook fires                 │
│  inject_context.py ──────────────────┐              │
│       │  recall(query=user_message)  │              │
│       ▼                              ▼              │
│  Moorcheh API ◄──── namespace: memanto_project_xyz   │
│       │                                              │
│       ▼  additionalSystemPrompt injected             │
│  Claude sees: "Remembered preferences:               │
│    - Always use FastAPI for REST APIs                │
│    - httpx over requests                            │
│    ..."                                              │
│                                                      │
│  ... Claude helps with endpoint ...                  │
│                                                      │
│       ▼  Stop hook fires                             │
│  capture_preferences.py ─────────────►  Moorcheh    │
│       Extracts new preferences from transcript       │
└─────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Set your API key
export MOORCHEH_API_KEY=your_key_here
# Or: cp .env.example .env && edit .env

# 3. Install Claude Code hooks
python3 install.py

# 4. Run the persistence demo (no Claude Code needed)
python3 demo/run_demo.py
```

## Step-by-Step Demo (Proves Cross-Session Persistence)

The demo simulates two separate Claude Code sessions:

```bash
python3 demo/run_demo.py
```

**Session 1** — Stores 5 engineering preferences (FastAPI, httpx, PostgreSQL, pytest, API versioning pattern) into Memanto. Process exits.

**Session 2** — NEW process. Queries Memanto with `"Help me add a new endpoint"`. Relevant preferences are recalled and printed, proving they survived the session boundary without any re-prompting.

Example output:
```
SESSION 1 — Storing engineering preferences
  ✅ Stored: Always use FastAPI for Python REST APIs
  ✅ Stored: Prefer httpx over requests for HTTP clients
  ✅ Stored: Decided to use PostgreSQL as the primary database
  ✅ Stored: Use pytest with fixtures — never unittest
  ✅ Stored: API versioning pattern: /api/v{n}/ prefix

SESSION 2 — New process, preferences recalled automatically
  User's first message: 'Help me add a new endpoint to the API'
  🧠 Injected into system context:
    1. [0.94] Always use FastAPI for Python REST APIs...
    2. [0.91] API versioning pattern: /api/v{n}/ prefix...
    3. [0.87] Prefer httpx over requests for HTTP clients...

SESSION 2 — Answering a synthesised question from memory
  Question: 'What database and HTTP client should I use?'
  Answer from Memanto:
  Use PostgreSQL for production and httpx as the HTTP client...
```

## File Structure

```text
examples/claudecode-skills-memanto/
├── README.md                         ← This file
├── requirements.txt                  ← memanto + moorcheh-sdk
├── .env.example                      ← API key template
├── memory_tools.py                   ← Core: remember/recall/answer wrappers
├── install.py                        ← Registers hooks in ~/.claude/settings.json
├── hooks/
│   ├── capture_preferences.py        ← Stop hook: captures preferences
│   └── inject_context.py             ← UserPromptSubmit hook: injects memories
└── demo/
    └── run_demo.py                   ← Cross-session persistence proof
```

## How the Hooks Work

### `capture_preferences.py` (Stop event)

Claude Code calls this with a JSON payload on stdin that includes the `transcript_path` — the path to the current session's JSONL transcript. The hook:

1. Reads the transcript file
2. Extracts assistant messages
3. Scans for preference/decision/constraint signals using pattern matching
4. Stores up to 10 new memories per session in Memanto

The namespace is derived from `md5(cwd)` so each project directory is isolated:
```python
namespace = f"memanto_project_{safe_name}_{md5_hash[:8]}"
```

### `inject_context.py` (UserPromptSubmit event)

Claude Code calls this before processing each user message. The hook:

1. Reads the user's prompt from the JSON payload
2. Calls `recall(query=prompt, top_k=5)` against the project's Memanto namespace
3. Filters results by similarity score (≥ 0.65)
4. Returns `{"additionalSystemPrompt": "Remembered preferences:\n- ..."}` to stdout

Claude Code merges this into the system context automatically.

## Manual Memory Management

You can also manage memories directly from Python:

```python
from memory_tools import remember, recall, answer, list_memories

# Store a preference manually
remember(
    title="Always type-annotate function signatures",
    content="All Python functions must have type annotations. "
            "Use mypy --strict in CI.",
    memory_type="constraint",
    tags=["python", "typing", "ci"],
)

# Recall relevant memories
memories = recall("How should I type this function?", top_k=3)

# Ask a synthesised question
resp = answer("What are our Python coding standards?")
print(resp)

# List everything
all_mems = list_memories()
```

## Memory Types

| Type | When to use |
|------|-------------|
| `preference` | Tool/library choices, style preferences |
| `decision` | Architectural decisions with rationale |
| `fact` | Stable project facts (DB type, deploy target, API base URL) |
| `pattern` | Reusable patterns (naming conventions, folder layout) |
| `constraint` | Hard rules that must never be violated |

## Connecting to Other Tools

After running the demo, the same project memories are accessible from any Memanto-connected tool:

```bash
# Access project memories from Cursor
memanto connect cursor --global

# Access from any Python script
from memory_tools import recall
memories = recall("What's our test strategy?")
```

## Contributing

This example was built for the [Memanto + mattpocock Developer Skills Challenge](https://github.com/moorcheh-ai/memanto/issues/508). PRs welcome.
