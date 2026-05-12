# 🐜 LangGraph + Memanto: Give Your Graph a Permanent Brain

> **Bounty submission for**: [moorcheh-ai/memanto#397](https://github.com/moorcheh-ai/memanto/issues/397)  
> **$100 USD Bounty** — LangGraph Integration Challenge

## Overview

This integration gives LangGraph agents **permanent, cross-session memory** powered by Memanto. Unlike standard LangGraph state (which is ephemeral per thread), Memanto stores semantic, episodic, and procedural memories that persist across conversations, sessions, and even different agents.

**Key innovation:** Cross-session recall — the agent remembers what it learned "yesterday" even in a brand-new thread with no shared state.

## Architecture

```
┌──────────────────────────────────────────┐
│           LangGraph StateGraph           │
│                                          │
│  ┌──────┐    ┌────────┐    ┌──────┐     │
│  │Agent │───►│ToolNode│───►│ END  │     │
│  └──┬───┘    └───┬────┘    └──────┘     │
│     │            │                      │
└─────┼────────────┼──────────────────────┘
      │            │
      ▼            ▼
┌──────────────────────────────────────────┐
│         Memanto Memory Layer             │
│                                          │
│  • remember()  →  Store new facts       │
│  • recall()    →  Retrieve by query      │
│  • answer()    →  Synthesise across mems  │
│                                          │
│  ↓ persists across sessions ↓            │
│  [semantic] [episodic] [procedural]      │
└──────────────────────────────────────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your API key

```bash
export MOORCHEH_API_KEY=your-api-key-here
```

### 3. Run the cross-session demo

```bash
python cross_session_demo.py
```

This simulates 3 sessions across multiple days, demonstrating that the agent recalls information stored in previous sessions (cross-session recall).

### 4. Run the customer support agent

```bash
python run_support_agent.py
```

## Cross-Session Recall Demo

The `cross_session_demo.py` script simulates three sessions:

| Session | Day | What Happens |
|---------|-----|-------------|
| **Session 1** | Monday | User tells agent their name, role, company, preferences, and current project |
| **Session 2** | Wednesday | User asks what they mentioned *last time* — agent recalls from Memanto (no thread state shared!) |
| **Session 3** | Friday | User asks for a full summary — agent synthesises across all stored memories |

This demonstrates the core bounty requirement: **Cross-Session Recall** — the agent remembers something from "yesterday" that isn't in the current thread's state.

## Tools

| Tool | Purpose | Schema |
|------|---------|--------|
| `memanto_remember` | Store a new fact in long-term memory | Pydantic v2 (Zod v4 compatible) |
| `memanto_recall` | Search persisted memories by natural-language query | Pydantic v2 (Zod v4 compatible) |
| `memanto_answer` | Synthesise an answer across multiple memories | Pydantic v2 (Zod v4 compatible) |

All tool inputs use **Pydantic v2 schemas** with `Field()` descriptors, making them compatible with Zod v4 structured output patterns (`import from "zod/v4"` equivalent in Python).

## x402 Payment Configuration

This agent supports **x402 payment protocol** for pay-per-invoke access:

```python
X402_CONFIG = {
    "payTo": "66dG5r5TD37ahhrsAMKUroxML9Cqto5jRduifiMgQQ3G",
    "network": "solana",
    "amount": 0.001,
}
```

## Files

| File | Description |
|------|-------------|
| `agent.py` | Core LangGraph StateGraph with Memanto tools |
| `memanto_tools.py` | LangChain Tool wrappers (Pydantic v2 schemas) |
| `cross_session_demo.py` | Cross-session recall demonstration |
| `run_support_agent.py` | Customer support agent example |
| `test_langgraph_memanto.py` | Unit tests (schemas, graph, x402 config) |
| `requirements.txt` | Python dependencies |

## Testing

```bash
# Unit tests (no API key needed for schema/graph tests)
python -m pytest test_langgraph_memanto.py -v

# Or with unittest
python test_langgraph_memanto.py
```

## Demo Video

🎬 See the `cross_session_demo.py` output for a walkthrough of cross-session recall:

- **Session 1**: Agent stores user's name, role, and preferences
- **Session 2**: Agent recalls everything without any shared thread state
- **Session 3**: Agent synthesises a complete summary from all memories

> *A 30-second recording of the demo output will be added after merge.*

## Why Memanto + LangGraph?

| Problem | Memanto Solution |
|---------|-----------------|
| LangGraph state is per-thread | Memanto persists across threads and sessions |
| No semantic search in thread state | Memanto recall uses semantic similarity matching |
| Cannot synthesise across memories | `memanto_answer` combines multiple stored facts |
| Each session starts from zero | Cross-session recall loads relevant context |

## License

MIT — same as the Memanto project.