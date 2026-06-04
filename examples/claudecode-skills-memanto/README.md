# Memanto + mattpocock/skills — Cross-Skill Memory Layer

> **Zero repeated instructions.** Memanto acts as a global, active memory companion across different skill executions in the [mattpocock/skills](https://github.com/mattpocock/skills) developer workflow.

## The Problem: Context Fragmentation

When you use `/tdd` in one terminal, `/grill-with-docs` in another, and `/handoff` in a third — each skill runs in isolation. Your architectural decisions, testing preferences, and codebase conventions must be re-explained every single time.

## The Solution: Memanto as Persistent Memory

This integration layer hooks into the skill lifecycle to:

1. **On skill start:** Query Memanto for memories relevant to the current file/task and inject them as context
2. **On skill complete:** Distill the interaction and store key learnings in Memanto's semantic memory

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   /tdd       │     │ /grill-docs  │     │   /handoff   │
│   skill      │     │   skill      │     │   skill      │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────────┐
│              Memanto Skill Hook Layer                     │
│  ┌─────────────────┐    ┌──────────────────────────────┐ │
│  │ on_skill_start() │    │ on_skill_complete()          │ │
│  │ → recall(query)  │    │ → remember(summary)          │ │
│  │ → inject context │    │ → distill via Moorcheh LLM   │ │
│  └─────────────────┘    └──────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                   Memanto Server                          │
│  • Semantic memory search (Moorcheh vector DB)           │
│  • 13 memory types (fact, decision, preference, ...)     │
│  • Confidence scoring + provenance tracking              │
│  • Cross-session persistence                             │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free: 100K ops/month)

### 2. Setup

```bash
cd examples/claudecode-skills-memanto

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

### 3. Run the Demo

```bash
# Session 1: Simulate a /tdd skill discovering testing preferences
python demo_cross_session.py session1

# Session 2: Simulate a /grill-with-docs skill — it remembers!
python demo_cross_session.py session2
```

### 4. Use in Your Workflow

#### Option A: Shell Wrapper

```bash
# Wrap any skill invocation
./skill-with-memanto.sh /tdd src/api/users.ts "Write tests for user signup"

# It will:
# 1. Show relevant memories from past sessions
# 2. Ask you to paste a summary when done
# 3. Store the summary in Memanto
```

#### Option B: Python API

```python
from memanto_skill_hook import SkillMemory

mem = SkillMemory()

# Before skill: get context
context = mem.on_skill_start(
    skill_name="/tdd",
    file_path="src/api/auth.ts",
    task_description="Write tests for auth endpoints",
)
print(context)  # inject into your prompt

# After skill: store learnings
mem.on_skill_complete(
    skill_name="/tdd",
    summary="Used Vitest + AAA pattern. Mocked auth middleware with vi.mock().",
    file_path="src/api/auth.ts",
)
```

#### Option C: CLI

```bash
# Pre-skill context retrieval
python -m memanto_skill_hook pre --skill /tdd --file src/auth.ts --task "Write tests"

# Post-skill memory storage
python -m memanto_skill_hook post --skill /tdd --file src/auth.ts \
    --summary "Used Vitest + AAA pattern. Mocked auth middleware."
```

#### Option D: Claude Code Hooks

Add to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Write|Edit",
      "hook": "python /path/to/claude_code_hook.py pre"
    }],
    "PostToolUse": [{
      "matcher": "Bash|Write|Edit",
      "hook": "python /path/to/claude_code_hook.py post"
    }]
  }
}
```

## Architecture

### Memory Types Used

| Type | When | Example |
|------|------|---------|
| `decision` | Architectural choices | "Use Vitest, not Jest" |
| `preference` | Coding style | "Prefer async/await over .then()" |
| `fact` | Codebase facts | "Auth middleware lives in src/middleware/auth.ts" |
| `instruction` | Explicit rules | "All API routes need unit + integration tests" |

### Trust & Confidence

Memanto's built-in trust system ensures memories are reliable:

- **Provenance tracking**: explicit_statement > validated > observed > inferred
- **Confidence scoring**: 0.0–1.0 with age decay
- **Contradiction detection**: Flags conflicting memories
- **Validation counting**: Repeated patterns get higher trust

## File Structure

```
examples/claudecode-skills-memanto/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template
├── memanto_skill_hook/
│   ├── __init__.py              # Package entry point
│   ├── __main__.py              # CLI entrypoint
│   └── memory.py                # Core SkillMemory implementation
├── skill-with-memanto.sh        # Shell wrapper for terminal use
├── claude_code_hook.py          # Claude Code hooks integration
└── demo_cross_session.py        # Interactive demo (run session1 then session2)
```

## How It Solves the Bounty Requirements

✅ **Global Memory Hook**: `SkillMemory` initializes Memanto on first use via Moorcheh credentials

✅ **Active Extraction**: `on_skill_complete()` passes interaction summaries to Memanto's backend LLM, which distills and stores the developer's "Engineering Profile"

✅ **Dynamic Injection**: `on_skill_start()` queries Memanto for memories relevant to the current file path/task and returns them as a concise system constraint

✅ **Zero Repeated Instructions**: Memories persist across sessions, skills, and terminal instances

## License

This example is part of the [Memanto](https://github.com/moorcheh-ai/memanto) project and follows the same license.
