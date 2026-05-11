# LangGraph + Memanto: Cross-Session Support Agent Memory

This example shows a LangGraph support workflow using **Memanto as long-term
memory outside LangGraph state**. The graph starts with an empty state on day
two, recalls memories written on day one, drafts a response grounded in those
memories, and writes a follow-up memory for the next session.

## What It Demonstrates

![LangGraph + Memanto demo](./demo.gif)

- **Cross-session recall**: day-two graph state does not contain yesterday's
  order or receipt preference, but Memanto retrieves both.
- **Long-term memory outside LangGraph state**: LangGraph coordinates nodes;
  Memanto owns durable semantic memory.
- **Typed memories**: the example stores `preference`, `fact`, and `event`
  memories with confidence and tags.
- **Minimal dependencies**: no LLM key is required for the deterministic demo;
  only `MOORCHEH_API_KEY` is needed for real Memanto persistence.

## Architecture

```text
Day 1 seed script
  -> Memanto remember(preference, fact)

Day 2 LangGraph run with empty state
  -> load_context node: Memanto recall(...)
  -> draft_response node: response grounded in retrieved memories
  -> write_followup_memory node: Memanto remember(event)
```

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `MOORCHEH_API_KEY`.

## Run With Real Memanto

```bash
python run_day_one.py
python run_day_two.py
```

The second command starts a fresh LangGraph run and still recalls the support
preference and delayed-order memory from the previous session.

## Offline Demo

Use this when recording or testing without a Moorcheh API key:

```bash
set OFFLINE_DEMO=true
python run_full_demo.py
python validate_offline.py
```

The offline path uses the same LangGraph nodes with an in-process memory adapter
so CI and reviewers can verify the workflow shape without secrets.

## Expected Output

```text
Day 2: new LangGraph run with empty short-term state

Retrieved long-term memories:
- [preference] maya prefers email receipts: maya wants receipts by email, not SMS.
- [fact] maya order status: maya has order A-1007 delayed by weather until Friday.

Agent response:
I found your saved preference and will send the receipt by email...
```

## 30-Second Recording Guide

This folder includes `demo.gif`, a 30-second visual walkthrough of the example
output. To record your own terminal version, run:

Record the terminal while running:

```bash
set OFFLINE_DEMO=true
python run_full_demo.py
```

Suggested caption:

> A LangGraph support agent starts a new session with no order details in state,
> then uses Memanto to recall yesterday's receipt preference and delayed-order
> memory before replying.

Add the final GIF/video link to this README when publishing the bounty PR.
