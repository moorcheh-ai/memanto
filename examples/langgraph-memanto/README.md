# LangGraph + Memanto: Cross-Session Support Agent

This example shows a LangGraph support workflow using Memanto as long-term
memory outside normal graph state. The first run stores customer context. The
second run uses a different LangGraph `thread_id` and a fresh state object, then
recalls the earlier detail from Memanto.

![LangGraph Memanto demo](assets/demo.gif)

## What It Demonstrates

- Cross-session recall: `run_today.py` remembers a detail stored by
  `run_yesterday.py`.
- Cross-thread recall: the demo uses `yesterday-thread` and `today-thread`.
- External long-term memory: LangGraph state carries only the current message;
  Memanto stores and retrieves the durable customer memory.
- No LLM key required: the example is deterministic so the memory behavior is
  easy to inspect.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `MOORCHEH_API_KEY`.

## Run The Demo

Run the two sessions separately:

```bash
python run_yesterday.py
python run_today.py
```

Or run the complete demo in one command:

```bash
python run_full_demo.py
```

Expected behavior:

1. `run_yesterday.py` stores Dana's onboarding preferences in Memanto.
2. `run_today.py` starts with a new state that only asks what to prioritize.
3. The recall node retrieves Dana's stored context from Memanto.
4. The response uses the recalled preferences even though they are absent from
   the current LangGraph state.

## File Structure

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- graph.py              # LangGraph nodes and graph assembly
|-- support_memory.py     # Memanto setup, remember, and recall helpers
|-- run_yesterday.py      # First run: stores durable customer context
|-- run_today.py          # Second run: recalls from a fresh thread
|-- run_full_demo.py      # One-command demo for recording
`-- assets/demo.gif       # 30-second walkthrough
```

## Why Memanto Is Outside LangGraph State

LangGraph checkpoints are useful for resuming state inside a thread. This demo
uses separate thread IDs to show a different capability: durable semantic memory
that any later graph run can search. The `SupportState` only contains the current
message and node outputs; the customer history is stored by
`MemantoSupportMemory.remember_customer_context()` and retrieved by
`MemantoSupportMemory.recall_customer_context()`.
