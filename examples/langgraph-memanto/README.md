# LangGraph + Memanto: Give Your Graph a Permanent Brain

A production-ready example of a **LangGraph agent** using **Memanto** as its persistent, cross-session memory layer.

## What This Demonstrates

- **Cross-Session Recall** — The agent remembers past conversations even after restart. Try: *"What did we discuss yesterday?"*
- **Semantic Memory Search** — Uses Memanto's vector search to find relevant past interactions
- **Typed Memories** — Stores conversations, facts, observations, and preferences as typed memory records
- **Zero Config** — Just set your Memanto API key and run

## Architecture

```
User Input
    │
    ▼
┌─────────────┐
│  Recall     │  ← Memanto recall() — semantic search
│  Memories   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Generate   │  ← GPT-4o-mini with memory context
│  Response   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Store      │  ← Memanto remember() — persist interaction
│  Memory     │
└─────────────┘
```

## Prerequisites

- Python 3.10+
- A Memanto API key (free tier available — see [memanto.moorcheh.ai](https://memanto.moorcheh.ai))
- An OpenRouter or OpenAI API key for the LLM

## Setup

```bash
# 1. Navigate to this example
cd memanto/examples/langgraph-memanto

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set API keys
cp .env.example .env
# Edit .env and add your MEMANTO_API_KEY and OPENAI_API_KEY

# 4. Run the demo
python agent.py
```

## Cross-Session Demo

Run it once:
```
👤 You: My name is Ivan and I love AI agents
👤 You: I need help researching LangGraph tools
```

Then restart — it remembers:
```
👤 You: What did we discuss last time?
🤖 Assistant: You mentioned you're interested in LangGraph tools...
```

## How It Works

| Component | Role |
|-----------|------|
| **LangGraph** | Manages the agent's state machine workflow |
| **Memanto API** | Stores/retrieves typed semantic memories |
| **GPT-4o-mini** | Generates responses with memory context |

The `memanto_tools.py` provides LangChain-compatible `remember()` and `recall()` functions that communicate with the Memanto REST API.

## Customization

- Change `AGENT_ID` in `.env` to share memory across multiple agents
- Add new memory types in `memanto_tools.py`
- Modify the system prompt in `agent.py` for different agent personalities
