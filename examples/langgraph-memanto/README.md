# LangGraph + Memanto: Customer Support Agent with Long-Term Memory

This directory contains a complete LangGraph integration example that uses **Memanto** as a persistent, cross-session memory layer for a customer support agent.

> **Note**: This example uses Memanto's Python SDK (`memanto.cli.client.sdk_client.SdkClient`) directly. No additional integration package is needed.

## Architecture

```
┌──────────┐    ┌───────────────┐    ┌─────────────────┐
│  START   │───>│ recall_memory │───>│ generate_reply  │
└──────────┘    └───────────────┘    └─────────────────┘
                                               │
                                   ┌───────────┴───────────┐
                                   │                       │
                                   v                       v
                           ┌───────────────┐        ┌─────────┐
                           │classify_store │        │   END   │
                           └───────────────┘        └─────────┘
                                   │
                                   v
                           ┌───────────────┐
                           │ store_memory  │──> END
                           └───────────────┘
```

**Flow**: Each user message triggers memory recall → contextual reply generation → classification of what's worth remembering → optional storage.

## What This Demonstrates

- **Cross-session memory persistence**: Session 1 stores customer preferences; Session 2 recalls them — even after restarting
- **LangGraph StateGraph workflow**: Conditional edges, typed state, composable nodes
- **Semantic recall**: Natural-language search over structured memories with 13 memory types
- **RAG-powered answers**: Direct question-answering over stored memories
- **Intelligent storage**: LLM-classified decisions about what's worth remembering

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) (or any OpenAI-compatible API)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Quick Start

### Option 1: Full Demo (recommended for recording)

```bash
python run_full_demo.py
```

Runs all three phases in one script: store → recall → RAG answer.

### Option 2: Two-Session Demo (best for proving persistence)

```bash
# Session 1: Agent learns about the customer
python run_session1_store.py

# Session 2: New session, agent recalls prior context
python run_session2_recall.py
```

This is the best way to prove that memories survive across sessions. You can even restart your machine between runs.

## Demo GIF / Video

<!-- TODO: Record a 30-second terminal GIF showing the two-session flow -->
<!-- Recommended tool: asciinema (https://asciinema.org) or ttyrec + ttygif -->

```
$ python run_session1_store.py
────────────────────────────────────────
  SESSION 1: Storing Customer Context
────────────────────────────────────────
[OK] Memanto agent 'customer-acme-001' activated

  Customer: Hi, I'm Jane from ACME Corp. We're on the Enterprise plan.
  Agent: Welcome back, Jane! Great to hear from ACME Corp...

  Customer: We prefer CSV format for reports.
  Agent: Noted! I'll make sure your reports are generated in CSV...

[OK] Session ended. Memories persist in Memanto.

$ python run_session2_recall.py
────────────────────────────────────────
  SESSION 2: Cross-Session Recall
────────────────────────────────────────
[OK] NEW session for 'customer-acme-001'

  Direct Memory Recall:
    [preference] Report format preference
      ACME Corp prefers CSV format over JSON...
    [relationship] Account manager
      Bob Williams is the primary contact...

  Customer: What report format do we prefer?
  Agent: Based on your previous conversations, your team prefers
         CSV format because the finance team finds it easier...
```

## File Structure

```
examples/langgraph-memanto/
├── README.md                  # This file
├── requirements.txt           # Python dependencies
├── .env.example               # API key template
├── memanto_tools.py           # Memanto toolkit (SDK wrapper)
├── agent.py                   # LangGraph StateGraph definition
├── run_session1_store.py      # Session 1: store customer context
├── run_session2_recall.py     # Session 2: recall (proves persistence)
└── run_full_demo.py           # Full demo in one script
```

## Key Design Decisions

### Why LangGraph StateGraph?

LangGraph's `StateGraph` provides:
- **Typed state** via dataclasses — easy to reason about data flow
- **Conditional edges** — the `should_store` function routes to storage only when needed
- **Composable nodes** — each step (recall, reply, classify, store) is independent and testable
- **Message history** via `add_messages` reducer — automatic conversation management

### Why Memanto over plain vector DB?

- **13 semantic memory types** (fact, preference, goal, decision, etc.) vs. flat text chunks
- **Confidence scoring** — each memory has a 0.0–1.0 confidence score
- **Structured metadata** — tags, provenance, timestamps
- **Built-in RAG** — the `answer` endpoint does retrieval + generation in one call
- **Cross-agent sharing** — multiple agents can share the same memory namespace

### Memory Classification

The `classify_exchange` node uses the LLM to decide what's worth storing. This avoids:
- Storing trivial greetings or small talk
- Duplicating already-known information
- Storing vague or unhelpful statements

The classifier extracts structured data (memory type, title, content, confidence, tags) for clean storage.

## Customization

### Using a different LLM

```bash
# Use GPT-4
OPENAI_MODEL=gpt-4o

# Use OpenRouter
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=anthropic/claude-sonnet-4

# Use a local model (e.g., Ollama)
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3
```

### Modifying the graph

Edit `agent.py` to:
- Add new nodes (e.g., escalation detection, sentiment analysis)
- Change the conditional routing logic
- Modify the system prompt
- Add tool calling for external APIs

## Bonus: Cursor Integration

After running the demo, access the same memories from Cursor:

```bash
memanto connect cursor --global
```

Then in Cursor, ask: *"Use memanto recall to find what we know about ACME Corp"*
