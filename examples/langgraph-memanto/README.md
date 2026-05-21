# LangGraph + Memanto Support Memory Demo

This example shows how to use Memanto as persistent cross-session memory for a
LangGraph workflow. Day 1 stores support context for a customer. Day 2 starts a
fresh graph run with no day 1 details in state, recalls the relevant memories
from Memanto, and drafts a follow-up response from those memories.

## What it demonstrates

- A LangGraph `StateGraph` with explicit store and recall nodes.
- Memanto-backed memory that survives between separate Python processes.
- A no-key local dry run path for contributors and CI.
- A realistic support-agent scenario: customer preferences, refund commitment,
  and product context recalled in a later session.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Moorcheh API key and Memanto agent ID to `.env`:

```bash
MOORCHEH_API_KEY=your_moorcheh_api_key_here
MEMANTO_AGENT_ID=langgraph-support-memory-demo
```

## Run with Memanto

Run the store step:

```bash
python run_day1_store.py
```

Then run recall in a separate process:

```bash
python run_day2_recall.py
```

Expected result: day 2 retrieves memories about Maya's support preferences,
dark-mode dashboard screenshots, refund escalation, and executive ops context.

## One-command demo

```bash
python run_full_demo.py
```

## No-key dry run

If you want to inspect the LangGraph flow before connecting a Moorcheh key, add these to `.env` or export them in your shell:

```bash
MEMANTO_DRY_RUN=true
MEMANTO_LOCAL_STORE=.memanto-langgraph-demo.json
```

Then run:

```bash
python run_day1_store.py
python run_day2_recall.py
```

The local JSON backend keeps the same interface as the live Memanto client, so
the graph code does not change when switching back to Memanto.

## Files

- `graph.py` builds the LangGraph workflow.
- `memory_adapter.py` provides the live Memanto client and local dry-run client.
- `run_day1_store.py` stores memories in one process.
- `run_day2_recall.py` recalls those memories in a later process.
- `run_full_demo.py` runs both store and recall paths in one graph invocation.
