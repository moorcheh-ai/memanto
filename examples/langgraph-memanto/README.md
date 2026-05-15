# LangGraph + Memanto: Persistent Cross-Session Agent Memory

A LangGraph agent that uses [Memanto](https://memanto.ai) as its long-term
memory layer. Memories stored in one session are retrieved in another —
the agent remembers what happened "yesterday" without anything in the
current conversation state.

## What This Demonstrates

- **Cross-Session Recall**: Session 1 stores context → Session 2 retrieves it
  from Memanto. Nothing is carried in conversation state between sessions.
- **Typed Semantic Memory**: 13 memory types with confidence scoring, used
  directly from LangGraph tools.
- **RAG over agent memory**: `memanto_answer` synthesizes insights from
  multiple stored memories.
- **Clean separation**: LangGraph handles the agent loop; Memanto handles
  persistence. No hybrid state management.

## Architecture

```
┌──────────────────────────────────┐
│         LangGraph Agent          │
│  ┌──────────┐  ┌──────────────┐  │
│  │  Session 1│  │  Session 2   │  │
│  │ (May 15)  │  │ (May 16)     │  │
│  │           │  │              │  │
│  │ remember ─┼──┼─ recall      │  │
│  │   ▲       │  │    │         │  │
│  └───┼───────┘  └────┼─────────┘  │
│      │               │            │
└──────┼───────────────┼────────────┘
       │               │
       ▼               ▼
┌──────────────────────────────────┐
│           Memanto                 │
│  ┌────────────────────────────┐  │
│  │  Persistent Memory DB       │  │
│  │  (survives across sessions) │  │
│  │  • preferences              │  │
│  │  • facts / bug reports      │  │
│  │  • decisions / escalations  │  │
│  └────────────────────────────┘  │
└──────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An OpenAI API key (for the LangGraph agent's LLM)

## Setup

```bash
# 1. Clone and enter the example directory
cd examples/langgraph-memanto

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Quick Start

Run the full demo (both sessions in one command):

```bash
python run_full_demo.py
```

## Step-by-Step Demo (Proves Persistence)

This is the recommended flow for demonstrating cross-session recall:

```bash
# Step 1: Session 1 — Agent handles a customer bug report
# The agent stores preferences, facts, and decisions in Memanto
python run_session_1.py

# Step 2: Session 2 (new session, next day) — Agent retrieves
# ALL context from Session 1 via memanto_recall
# This proves memories persist across sessions!
python run_session_2.py
```

**What happens:**
1. Session 1: Alice reports a dark-mode chart bug. The agent stores her
   preferences, the bug details, and the escalation decision in Memanto.
2. Session 2 (next day): Alice asks "any update on that bug?" The agent
   calls `memanto_recall` and retrieves everything from yesterday —
   preferences, bug details, decisions — without Alice repeating herself.

## How It Works

### Tool-Based Integration

LangGraph's `create_react_agent` is given three Memanto tools:

| Tool | What the agent uses it for |
|------|---------------------------|
| `memanto_remember` | Store preferences, facts, decisions |
| `memanto_recall` | Search past memories by natural language |
| `memanto_answer` | Synthesize insights from multiple memories (RAG) |

This is the same tool-based pattern used in the CrewAI integration, but
adapted for LangGraph's tool interface (`@tool` from `langchain_core`).

### Namespace Design

All sessions share one Memanto agent ID (`langgraph-customer-support`),
mapping to a single namespace. This is intentional: the agent should
access all past interactions from the same memory pool. Different use
cases should use different agent IDs.

### Why Tool-Based (Not State-Based)

LangGraph has built-in state persistence via checkpointer, but that's
tied to a single thread. Memanto provides:

| Feature | LangGraph Checkpointer | Memanto |
|---------|----------------------|---------|
| Cross-session recall | Same thread only | Any session |
| Semantic search | No | Yes (Moorcheh) |
| Memory types | Untyped | 13 semantic types |
| Confidence scoring | No | Yes (0.0–1.0) |
| RAG synthesis | No | Yes (`answer`) |
| Temporal queries | No | Yes (as-of, changed-since) |

## File Structure

```
examples/langgraph-memanto/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
├── agent.py               # Memanto tools + agent builder
├── run_session_1.py       # Session 1: first interaction
├── run_session_2.py       # Session 2: cross-session recall
└── run_full_demo.py       # Both sessions in one command
```

## Customization

### Using a different LLM

```bash
export LLM_MODEL="gpt-4o"  # or any OpenAI-compatible model
```

### Creating your own agent

```python
from agent import MemantoSetup, build_agent

setup = MemantoSetup(api_key="your-key")
client = setup.setup(agent_id="my-custom-agent")

agent = build_agent(
    client=client,
    agent_id="my-custom-agent",
    system_prompt="You are a helpful assistant with persistent memory.",
    model="gpt-4o-mini",
)

result = agent.invoke({"messages": [("user", "Hello!")]})
print(result["messages"][-1].content)

setup.teardown("my-custom-agent")
```

## Learn More

- [Memanto Documentation](https://docs.memanto.ai)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
