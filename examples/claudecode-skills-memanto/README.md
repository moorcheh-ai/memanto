# Claude Code Skills + Memanto Memory Bridge

This example shows how to integrate [Memanto](https://memanto.ai/) as a persistent memory layer for [mattpocock/skills](https://github.com/mattpocock/skills)-style developer workflows — including Claude Code's `/grill-with-docs`, `/tdd`, `/handoff`, and other command-line skills.

## The Problem: Context Fragmentation

The `mattpocock/skills` ecosystem provides sharp, single-purpose command-line primitives. But each skill execution is isolated — when you run `/tdd` to add rate limiting to your auth service, then later run `/grill-with-docs` to document it, the documentation skill has no memory of the architectural decisions made during the TDD session.

**The result:** You repeat yourself constantly. "We use Redis for distributed state." "The connection string is `REDIS_URL`." "We use token buckets, not leaky buckets." Over and over, across every new terminal session.

## The Solution: Engineering Profile

Memanto acts as a global, active memory companion that persists across all skill executions. The `SkillMemoryBridge` wraps any skill with two lifecycle hooks:

```text
                 ┌─────────────────────────────────────────────────┐
                 │              Developer Skill Execution           │
                 │                                                  │
  before_skill() │  ┌──────────────┐    ┌──────────────────────┐  │
  ───────────────┼─►│ Query Memanto│    │  Inject memories as  │  │
                 │  │ for relevant │───►│  system constraints  │  │
                 │  │  memories    │    │  into skill prompt   │  │
                 │  └──────────────┘    └──────────────────────┘  │
                 │                                                  │
                 │         [Skill executes with context]           │
                 │                                                  │
  after_skill()  │  ┌──────────────┐    ┌──────────────────────┐  │
  ───────────────┼─►│ Distill key  │    │  Store to Memanto    │  │
                 │  │ learnings    │───►│  Engineering Profile  │  │
                 │  │ from output  │    │  (persistent memory)  │  │
                 │  └──────────────┘    └──────────────────────┘  │
                 └─────────────────────────────────────────────────┘
```

## Two Modes

| Mode | When | API Key Required |
|---|---|---|
| **Local Preview** | `LOCAL_PREVIEW=true` or no API key set | No |
| **Live Memanto** | `MOORCHEH_API_KEY` is set | Yes (free tier available) |

Local Preview uses a JSONL file as a mock memory store — perfect for testing, CI, and evaluating the bridge without any credentials.

## Quick Start

### Option A: Local Preview (no API key required)

```bash
cd examples/claudecode-skills-memanto
pip install -r requirements.txt

# Run the demo
python demo.py

# Run validation tests
python validate.py
```

### Option B: Live Memanto API

```bash
# Get a free API key at https://console.moorcheh.ai/api-keys
export MOORCHEH_API_KEY=your_key_here

pip install -r requirements.txt
python demo.py
```

## Usage in Your Skill Workflow

```python
from skill_memory_bridge import SkillMemoryBridge

bridge = SkillMemoryBridge()

# 1. Before running a skill — get relevant context to inject
context = bridge.before_skill(
    skill_name="tdd",
    task_description="Add rate limiting to the auth service"
)
# context is a formatted string ready to inject into the skill's system prompt
# e.g.: "## Engineering Profile\n1. [tdd] We use Redis for distributed state..."

# 2. After the skill completes — store what was learned
bridge.after_skill(
    skill_name="tdd",
    summary="Used token bucket rate limiter in auth/rate_limit.py. Redis via REDIS_URL.",
    tags=["tdd", "auth", "redis", "rate-limiting"]
)
```

### Integration with Claude Code

Add the bridge to your Claude Code skill wrapper:

```python
# In your skill runner / MCP tool
import subprocess
from skill_memory_bridge import SkillMemoryBridge

bridge = SkillMemoryBridge()

def run_skill(skill_name: str, task: str) -> str:
    # Inject memories before execution
    memory_context = bridge.before_skill(skill_name, task)

    # Build the prompt with injected context
    prompt = f"{memory_context}\n\n{task}" if memory_context else task

    # Run the skill (example: Claude Code CLI)
    result = subprocess.run(
        ["claude", f"/{skill_name}", prompt],
        capture_output=True, text=True
    )

    # Store learnings after execution
    bridge.after_skill(skill_name, result.stdout[:500])

    return result.stdout
```

## Demo Transcript

Running `python demo.py` produces this output (abbreviated):

```text
SESSION 1: /tdd — Auth Service Rate Limiting
🧠 [before_skill:tdd] Querying memory...
   No relevant memories found.
⚙️  [/tdd executing...] Writing tests for token bucket rate limiter...
💾 [after_skill:tdd] Storing memory: Implemented token bucket rate limiter...

SESSION 2: /grill-with-docs — Auth Module Documentation
🧠 [before_skill:grill-with-docs] Querying memory...
   Found 1 relevant memory.
📋 Injected context:
   1. [tdd] Implemented token bucket rate limiter in auth/rate_limit.py.
      Used Redis for distributed state. Key decision: 100 req/min per user.

SESSION 4: /tdd — Payment Service (Redis also used here)
🧠 [before_skill:tdd] Querying memory...
   Found 3 relevant memories.
📋 Injected context (Redis memory surfaces from auth work):
   1. [tdd] Implemented token bucket rate limiter... Used Redis...
   2. [grill-with-docs] Redis connection string must be set via REDIS_URL env var.
   3. [handoff] Handoff document covers rate limiter implementation, Redis dependency.

✅ Key insight: In SESSION 4, the Redis knowledge from SESSION 1 was
   automatically surfaced — no repeated instructions needed.
```

## Validation

```bash
python validate.py
```

Expected output:
```text
  ✅ PASS: Bridge initializes correctly
  ✅ PASS: after_skill() stores memory
  ✅ PASS: before_skill() returns empty when no memories
  ✅ PASS: before_skill() returns relevant memories
  ✅ PASS: Cross-skill memory retrieval works
  ✅ PASS: Multiple memories stored and retrieved
  ✅ PASS: Tags improve retrieval precision

Results: 7/7 passed
✅ All tests passed!
```

## File Structure

```text
examples/claudecode-skills-memanto/
├── skill_memory_bridge.py   # Core bridge: SkillMemoryBridge class
├── demo.py                  # Runnable demo (4 simulated skill sessions)
├── validate.py              # Automated validation suite (7 tests)
├── requirements.txt         # Dependencies
├── .env.example             # Environment variable template
└── README.md                # This file
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `MOORCHEH_API_KEY` | For live mode | Get free at [console.moorcheh.ai](https://console.moorcheh.ai/api-keys) |
| `LOCAL_PREVIEW` | No | Set to `true` to force local JSONL mode |
| `MEMANTO_NAMESPACE` | No | Namespace for memory isolation (default: `developer-skills`) |

## Prerequisites

- Python 3.10+
- No API key required for local preview mode
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) for live mode (free tier: 100K ops/month)
