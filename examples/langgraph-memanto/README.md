# LangGraph + Memanto Integration

This example demonstrates a **LangGraph stateful agent** using **Memanto** as its persistent, long-term memory layer — with cross-session recall that survives across runs, days, and agent restarts.

> **The Challenge:** LangGraph is great for stateful agents, but its built-in state is ephemeral — lost when the graph finishes. Memanto fills that gap: an active memory agent with `remember`, `recall`, and `answer` primitives that give LangGraph agents a **permanent brain**.

![LangGraph + Memanto Demo](https://via.placeholder.com/800x450.png?text=LangGraph+Memanto+Demo+%7C+30s+GIF) <!-- Replace with your 30-second screen recording link -->

## What This Demonstrates

- **Cross-session recall** — Run the agent today, run it tomorrow, it remembers everything
- **Typed semantic memory** — Preferences, facts, decisions, events each stored with type metadata
- **LangGraph state machine** — A structured support agent with conditional routing
- **Provenance + confidence** — Every memory knows where it came from and how confident we are

## Architecture

```
┌─────────────────────────────────────────────────┐
│               LangGraph Agent                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Router  │───▶│  Process │───▶│  Respond │  │
│  └──────────┘    └──────────┘    └──────────┘  │
│        │              │               │          │
│        ▼              ▼               ▼          │
│  ┌─────────────────────────────────────────┐    │
│  │          Memanto (CLI/REST)              │    │
│  │  remember / recall / answer primitives   │    │
│  └─────────────────────────────────────────┘    │
│                         │                        │
│                         ▼                        │
│              ┌─────────────────────┐             │
│              │  Moorcheh Engine    │             │
│              │  (no-indexing DB)   │             │
│              └─────────────────────┘             │
└─────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenRouter API key](https://openrouter.ai/keys) (for LangGraph's LLM)

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
cp .env.example .env
# Edit .env — add your MOORCHEH_API_KEY and OPENROUTER_API_KEY
```

## Step-by-Step Demo

### Phase 1: Store Customer Profile (Session A)

```bash
python run_customer_service.py
```

The agent greets the customer, learns their preferences and facts, and stores them as typed memories in Memanto.

### Phase 2: Cross-Session Recall (Session B — full restart)

```bash
python run_followup.py
```

The agent starts fresh (new LangGraph state) but recalls everything from Session A via Memanto. This **proves** cross-session persistence.

### Phase 3: Full Pipeline

```bash
python run_full_pipeline.py
```

Runs both phases in one script for quick testing.

## File Structure

```text
examples/langgraph-memanto/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template
├── agent.py                     # LangGraph graph + nodes
├── memory.py                    # Memanto wrapper (CLI-based)
├── run_customer_service.py      # Session A: store profile
├── run_followup.py              # Session B: cross-session recall
└── run_full_pipeline.py         # Full pipeline runner
```

## Social Traction

⭐ [Star the Memanto repo](https://github.com/moorcheh-ai/memanto) to help reach 1,000 stars!

After running the demo:
1. Record a 30-second screen recording showing cross-session recall
2. Post it on X/LinkedIn/Reddit with **#Memanto** and **@moorcheh-ai**
3. Link your post in this PR description
