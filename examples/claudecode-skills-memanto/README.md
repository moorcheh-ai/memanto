# Claude Code Skills + Memanto: Cross-Skill Memory

> **Eliminate context fragmentation across Claude Code skill sessions.**
>
> Zero repeated instructions. Your architectural decisions, codebase conventions,
> and coding preferences automatically follow you between skills.

## The Problem

Claude Code skills are powerful but isolated. When you use `/architect` to design
a system, then `/tdd` to write tests, then `/grill-with-docs` to review — each
skill starts from zero context. You waste time re-explaining decisions.

## The Solution

**Memanto** acts as a global memory layer. It:
1. **Listens** to skill inputs/outputs
2. **Distills** architectural choices, patterns, and preferences
3. **Injects** them back when subsequent skills need that context

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Get your free API key
# Visit: https://moorcheh.ai

# 3. Set environment variable
export MOORCHEH_API_KEY="your-key-here"
export DEVELOPER_ID="your-github-username"

# 4. Run the demo
python demo.py
```

## Integration

### In your skill hook (pre-execution)

```python
from skill_memory import SkillMemory

mem = SkillMemory()
mem.setup(developer_id="your-id")

# Before any skill runs
ctx = mem.pre_execute(
    skill_name="grill-with-docs",
    file_paths=["src/auth/login.py"],
)

# mem.injected_context now contains relevant memories
# from past skill sessions. Append to your skill's prompt.
```

### In your skill hook (post-execution)

```python
# After skill completes
mem.post_execute(
    ctx,
    summary="Reviewed auth module. Found JWT exp in login handler.",
    key_decisions=["Switch to refresh token rotation"],
    code_patterns=["Use pytest-asyncio for auth tests"],
)
```

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Claude Code                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │architect │  │   tdd    │  │ grill-with-docs  │   │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
│       │             │                 │              │
│       └─────────────┼─────────────────┘              │
│                     │                                │
│              ┌──────▼──────┐                         │
│              │ SkillMemory │  ◄── Memanto SDK        │
│              │ (hooks)     │                         │
│              └──────┬──────┘                         │
└─────────────────────┼────────────────────────────────┘
                      │
              ┌───────▼────────┐
              │    Memanto     │
              │  (Moorcheh)    │
              │  Semantic RAG  │
              └────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `skill_memory.py` | Core SkillMemory class + hook generator |
| `demo.py` | Full demonstration of cross-skill memory |
| `hooks/` | Generated pre-execution hook scripts |

## Requirements

- Python 3.10+
- `memanto` package (auto-installed via pip)
- Moorcheh API key (free tier available at moorcheh.ai)
