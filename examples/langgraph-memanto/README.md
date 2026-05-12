# LangGraph + Memanto: Cross-Session Memory Demo

This directory contains a multi-session LangGraph example demonstrating **persistent, cross-session memory** using Memanto.

## What This Demonstrates

| Capability | How It's Shown |
|---|---|
| **Cross-session persistence** | `run_research.py` (Session 1) stores memories → `run_recall.py` (Session 2) retrieves them after teardown |
| **Semantic recall** | Natural-language queries return relevant memories even with different wording |
| **RAG over memory** | The `memanto_answer` tool synthesizes answers from multiple stored facts |
| **Typed memory** | Memories can be tagged as `fact`, `observation`, `decision`, etc. |

## Demo Recording

> 🎥 **A 30-second terminal recording** will be added here once reviewed.
> Run the steps below yourself to verify cross-session persistence.

The demo flow:
1. `python run_research.py` — stores three memories (Session 1)
2. `python run_recall.py` — recalls all three from a fresh session (Session 2)
3. Run `run_recall.py` again hours/days later — memories still available

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

## Run the Demo

### Step 1: Store memories (Session 1)

```bash
python run_research.py
```

Expected output:
```
=== Storing Session 1 memories ===

Memory stored successfully.
  ID: 7a1b2c3d-...
  Type: fact
  Title: LLM Memory Survey 2025
  Confidence: 0.9
...
Session 1 complete. Memories persist in Memanto.
```

### Step 2: Recall memories (Session 2)

Run this immediately or hours later — the memories persist:

```bash
python run_recall.py
```

Expected output:
```
=== Session 2 — Recalling memories from Session 1 ===

--- Query: 'LLM memory survey findings' ---
Found 1 memories for 'LLM memory survey findings':
  1. [fact] LLM Memory Survey 2025 (confidence: 0.9) [tags: research, llm, memory]
     Memory-augmented LLMs improve task completion by 34%...
...
Session 2 complete. Cross-session memory verified!
```

## Integration Package

The LangGraph tool classes used by this demo live at [`integrations/langgraph-memanto/`](../../integrations/langgraph-memanto/).

## Payment / Bounty Wallets

- **EVM (ETH, BASE, etc.):** `0x04836c595d9633abeb120b7b68f57e6e834b0c6c`
- **SOL (Solana):** `9r7u8mET3M5rvDf4txqzkMsvaGXk9BUoNtZNZfv685VB`
