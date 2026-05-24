# LangGraph + Memanto: Persistent Memory for Stateful Agents

This example demonstrates how to use **Memanto** as the long-term memory layer for a **LangGraph** agent, enabling persistent context across sessions.

## What This Demonstrates

- **Session-persistent memory**: A customer support agent remembers user preferences and past issues across disjointed conversations
- **Typed semantic memory**: Uses Memanto's 13 memory categories (fact, preference, decision, etc.)
- **Zero ingestion latency**: Memories are retrievable immediately after storage
- **Graph RAG retrieval**: 2-hop knowledge graph traversal connects related memories

## Architecture

```text
User Query → LangGraph Agent → Memanto Recall (context) → LLM Response
                    ↓
            Memanto Remember (new info)
```

## Prerequisites

- Python 3.10+
- [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An OpenAI-compatible API key (for the LLM)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export MOORCHEH_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"  # or any OpenAI-compatible provider
```

## Run the Demo

```bash
python customer_support_agent.py
```

This runs a scripted multi-turn customer support agent that:
1. Remembers your product preferences
2. Recalls past issues you've reported
3. Builds a knowledge graph of your relationship with the service

## Key Concepts

### Memory Types Used
- `preference`: User likes/dislikes (e.g., "prefers email over chat")
- `fact`: Objective information (e.g., "uses Pro plan")
- `issue`: Past problems (e.g., "had login issue on 2024-03-15")
- `decision`: Choices made (e.g., "upgraded to annual billing")

### Why LangGraph + Memanto?

LangGraph manages conversation state within a session. Memanto extends this state across sessions, giving your agent a true "permanent brain."
