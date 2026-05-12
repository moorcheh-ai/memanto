# LangGraph + Memanto: Long-Term Memory for Stateful Agents

![LangGraph + Memanto](https://img.shields.io/badge/LangGraph-Memanto-8A2BE2)

This example demonstrates **Memanto as the long-term memory layer** for a [LangGraph](https://langchain-ai.github.io/langgraph/) agent — proving **cross-session recall** that persists outside of the graph's state.

## What This Demonstrates

| Capability | How It Works |
|---|---|
| **Cross-session recall** | Agent remembers facts from "yesterday" in a brand-new thread |
| **Typed semantic memory** | 13 memory categories (`fact`, `preference`, `goal`, `decision`, etc.) |
| **Grounded answers (RAG)** | `answer` tool generates responses from stored memory context |
| **Zero graph state bloat** | Long-term data lives in Memanto, not the LangGraph state |
| **Automatic context loading** | Agent recalls relevant memories at the start of each turn |

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph Agent                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ remember │    │  recall  │    │  answer  │  ← tools      │
│  │   tool   │    │   tool   │    │   tool   │              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │               │               │                     │
└───────┼───────────────┼───────────────┼─────────────────────┘
        │               │               │
        ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Memanto (REST API)                         │
│         Persistent, typed semantic memory layer              │
│         ˑ remembers ˑ recalls ˑ answers ˑ                   │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                 Moorcheh Semantic Database                    │
│         No-indexing, sub-90ms retrieval, serverless         │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) (or OpenRouter with a free model)

## Quick Start

```bash
# 1. Navigate to this example
cd examples/langgraph-memanto

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY

# 5. Start the Memanto server (in a separate terminal)
memanto serve
# Or with Docker: docker-compose up -d

# 6. Run the cross-session demo
python run_cross_session.py
```

## Demos

### 🧪 Cross-Session Recall (The Main Event)

```bash
python run_cross_session.py
```

This runs two independent LangGraph sessions:

1. **Session A** — Alice introduces herself (name, job, preferences). The agent stores memories via Memanto.
2. **Session B** — A brand-new thread with no history. Alice asks "Do you remember me?" The agent uses Memanto's `recall` tool to retrieve yesterday's memories.

The script also verifies directly via the Memanto API that memories were persisted.

### 🎮 Interactive Chat

```bash
python agent.py
```

An interactive REPL where you can chat with the agent. It will:
- Remember your preferences automatically
- Recall your name and past conversations in new sessions
- Answer questions based on stored memories

## File Structure

```text
examples/langgraph-memanto/
├── README.md                  # This file
├── requirements.txt           # Python dependencies
├── .env.example               # API key template
├── memanto_client.py          # Memanto REST API client wrapper
├── agent.py                   # LangGraph agent with Memanto tools
└── run_cross_session.py       # Cross-session recall demo
```

## How It Works

### 1. Memanto Tools

Three LangGraph tools wrap Memanto's core primitives:

| Tool | Maps To | Purpose |
|---|---|---|
| `remember_tool` | `POST /remember` | Store a memory with type + confidence |
| `recall_tool` | `POST /recall` | Semantic search over stored memories |
| `answer_tool` | `POST /answer` | Grounded RAG answer from memory |

### 2. Agent Loop

The agent automatically:
1. Checks memory via `recall` at the start of each conversation
2. Stores important user info via `remember`
3. Uses `answer` for grounded responses

### 3. Cross-Session

Because the Memanto server persists data independently, starting a new LangGraph thread doesn't lose the agent's memories — the agent can `recall` facts stored in any previous session.

## Expected Output (Cross-Session Demo)

```
══════════════════════════════════════════════════════════════════
  PHASE 1: Session A — User introduces themselves
══════════════════════════════════════════════════════════════════

  [User] Hi! I'm Alice. I'm a frontend developer working on React projects.
  [Agent] Nice to meet you, Alice! Let me note that down...

  [User] I prefer dark mode for all my tools and I like concise answers.
  [Agent] Got it! Dark mode and concise answers — remembered.

══════════════════════════════════════════════════════════════════
  PHASE 2: Session B — New session, recall past memories
══════════════════════════════════════════════════════════════════

  [User] Hi again! Do you remember anything about me?
  [Agent] Yes! Your name is Alice, you're a frontend developer...
```

## Customization

### Memory Types

Use these semantic types for cleaner retrieval:

- `fact` — General information
- `preference` — User likes/dislikes
- `goal` — User objectives
- `decision` — Choices made
- `commitment` — Promises/agreements
- `relationship` — Personal connections
- `event` — Time-bound occurrences
- `observation` — Inferred patterns

### LLM Provider

Edit `.env` to switch models:

```ini
OPENAI_MODEL=gpt-4o          # Use a more capable model
# or use OpenRouter:
# LLM_PROVIDER=openrouter
# OPENROUTER_MODEL=openrouter/anthropic/claude-sonnet-4
```
