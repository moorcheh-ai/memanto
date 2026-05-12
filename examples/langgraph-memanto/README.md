# LangGraph + Memanto: Customer Support Agent

A LangGraph-powered customer support agent that uses Memanto for persistent, cross-session memory.

## What It Does

- Processes user support requests through a LangGraph state machine
- Retrieves relevant memories from past sessions via Memanto (cross-session recall)
- Stores new facts and preferences back to Memanto
- The agent remembers user details from "yesterday" — try asking about preferences you set in a previous run

## How Cross-Session Recall Works

1. **Session 1**: User says "My name is Alice and I prefer email notifications"
   → Agent stores `fact` (name=Alice) and `preference` (email notifications) to Memanto

2. **Session 2** (next day, new LangGraph state): User says "What do you know about me?"
   → Agent retrieves memories from Memanto via semantic search
   → Agent responds: "Your name is Alice, and you prefer email notifications."

The memory lives in Memanto's persistent store, not in LangGraph's in-memory state.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
cp .env.example .env
# Edit .env with your API keys

# Run the agent
python customer_support_agent.py alice "Hi, my name is Alice and I prefer email updates"

# In a new session, the agent will remember:
python customer_support_agent.py alice "What do you remember about me?"
```

## Architecture

```
User → [retrieve_memories] → [call_llm] → [extract_memories] → Response
          ▲                                              │
          │                Memanto Store                 │
          └──────────────────────────────────────────────┘
```

- `retrieve_memories`: Queries Memanto for relevant past memories
- `call_llm`: Calls Claude with conversation + cross-session context
- `extract_memories`: Stores new facts/preferences to Memanto

## Demo

[Watch demo GIF](https://example.com/memanto-langgraph-demo.gif) — 30-second walkthrough showing cross-session recall in action.
