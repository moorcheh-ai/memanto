# LangGraph + Memanto: Long-Term Memory for Stateful Agents

This example demonstrates how to use **Memanto** as the long-term memory layer for a [LangGraph](https://langchain-ai.github.io/langgraph/) agent — giving your graph a "permanent brain" that persists across sessions, conversations, and agent restarts.

## What This Demonstrates

| Capability | How It Works |
|---|---|
| **Cross-session recall** | The agent remembers facts, preferences, and decisions from earlier sessions that aren't in the current LangGraph state |
| **Typed semantic memory** | Memories are stored with semantic types (fact, preference, decision, etc.) for cleaner retrieval |
| **Memory-grounded answers** | The agent uses Memanto's `answer` endpoint to generate responses grounded in stored memories |
| **No indexing delay** | Memories are searchable the instant they're stored — zero ingestion latency |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Agent                       │
│                                                          │
│   ┌──────────┐    ┌─────────────┐    ┌──────────────┐   │
│   │  User     │───▶│  Think      │───▶│  Remember /  │   │
│   │  Input    │    │  (LLM)      │    │  Recall      │   │
│   └──────────┘    └─────────────┘    └──────┬───────┘   │
│                                              │           │
│                                              ▼           │
│                                      ┌──────────────┐   │
│                                      │  Respond     │   │
│                                      │  to User     │   │
│                                      └──────────────┘   │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
       ┌──────────────────────────────────────┐
       │          Memanto REST API             │
       │  (localhost:8000 or remote server)    │
       │                                       │
       │  POST /api/v2/agents/{id}/remember    │
       │  POST /api/v2/agents/{id}/recall      │
       │  POST /api/v2/agents/{id}/answer      │
       └──────────────────────────────────────┘
                        │
                        ▼
       ┌──────────────────────────────────────┐
       │          Moorcheh SDK                 │
       │  (No-index semantic search engine)   │
       └──────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- A running Memanto server (or use Memanto CLI)
- An LLM API key (OpenAI, Anthropic, etc.) for LangGraph

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
cp .env.example .env
# Edit .env to add your MOORCHEH_API_KEY, LLM_API_KEY, and MEMANTO_URL
```

## Running the Example

### Step 1: Start Memanto Server
```bash
# Install and start Memanto
pip install memanto
memanto server start
```
Or use a hosted Memanto instance at your MEMANTO_URL.

### Step 2: Run Cross-Session Demo
This demo proves memories persist across sessions:

```bash
# Session 1 — Store memories as a customer support agent
python run_customer_support.py --session 1

# Session 2 — Start a new conversation, agent recalls past interactions
python run_customer_support.py --session 2

# Full cross-session pipeline
python run_cross_session.py
```

## How It Works

### Memory Client (`langgraph_memanto/memory_client.py`)
A lightweight HTTP client that communicates with the Memanto REST API. All operations go through:
- `remember()` — store a typed memory (fact, preference, decision, etc.)
- `recall()` — search memories by semantic relevance
- `answer()` — get an LLM-grounded response from your memories

### LangGraph Agent (`langgraph_memanto/agent.py`)
A stateful LangGraph workflow with three nodes:
1. **Think** — The LLM decides what to remember or recall
2. **Memory** — Stores/retrieves memories via Memanto
3. **Respond** — Generates the user-facing response

### State (`langgraph_memanto/state.py`)
Extends LangGraph's built-in state with Memanto agent/session fields for seamless memory integration.

## File Structure

```
examples/langgraph-memanto/
├── README.md                         # This file
├── requirements.txt                  # Python dependencies
├── .env.example                      # API key template
├── run_customer_support.py           # Customer support agent demo
├── run_cross_session.py              # Cross-session recall demo
└── langgraph_memanto/
    ├── __init__.py
    ├── agent.py                      # LangGraph agent definition
    ├── memory_client.py              # Memanto REST API client
    ├── nodes.py                      # LangGraph graph nodes
    └── state.py                      # State type definitions
```
