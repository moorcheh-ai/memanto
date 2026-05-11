# LangGraph + Memanto: Cross-Session Agent Memory

This example shows a LangGraph support workflow using **Memanto** as its durable long-term memory layer. The graph keeps only the current message in LangGraph state; customer profile facts are stored and recalled from Memanto under a shared agent namespace.

## Demo Video

30-second demo GIF/video: [demo.gif](./demo.gif)

## What It Demonstrates

- **Cross-session recall**: session 2 remembers Avery's product, deadline, and response preference from session 1 even though those fields are not present in session 2 state.
- **Memory outside graph state**: LangGraph orchestrates the workflow while Memanto persists the facts.
- **Repeatable local validation**: `run_full_demo.py --dry-run` proves the workflow without API keys; the same graph runs against the real Memanto SDK when keys are configured.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For the real Memanto-backed run, edit `.env` and set `MOORCHEH_API_KEY`. The dry-run does not need any keys.

## Quick Verification Without API Keys

```bash
python run_full_demo.py --dry-run
```

Expected evidence in the output:

- Session 1 includes a `remembered_id`.
- Session 2 input has no `profile`.
- Session 2 `reply` includes the remembered Friday demo deadline and checklist preference.

## Real Cross-Session Demo

Run these commands in separate shells or at different times. Both use the same `MEMANTO_AGENT_ID`, so the second session can recall memory written by the first.

```bash
python run_seed_session.py
python run_recall_session.py
```

The second command starts with only:

```json
{
  "customer": "Avery",
  "message": "Can you continue from yesterday? I forgot the details."
}
```

It recalls Avery's durable support profile from Memanto and drafts the response from retrieved memory rather than from current LangGraph state.

## File Structure

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── requirements.txt
├── graph.py
├── memanto_memory.py
├── run_full_demo.py
├── run_seed_session.py
└── run_recall_session.py
```

## Why This Design

LangGraph should own orchestration and short-lived state. Memanto should own durable facts that need to survive process restarts, separate graph invocations, or future agents. The `MemoryClient` protocol in `memanto_memory.py` keeps that boundary explicit and makes the example testable with a mock client before using the real `SdkClient`.
