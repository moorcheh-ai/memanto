# LangGraph + Memanto Cross-Session Memory

This example shows a LangGraph customer-support workflow using Memanto as the long-term memory layer outside LangGraph thread state. Session one stores support details, then session two starts with a different `thread_id` and recalls those details only through the memory adapter.

30-second demo GIF: [demo.gif](demo.gif)

## What This Demonstrates

- **Cross-session recall**: a fresh graph invocation recalls details from a previous run.
- **Memanto boundary**: only the memory adapter persists data; LangGraph receives no checkpointer.
- **Offline review path**: the local JSON backend proves the workflow without API keys.
- **Live Memanto path**: the same graph can use `SdkClient.remember()` and `SdkClient.recall()`.

## Architecture

```text
customer message
      |
      v
LangGraph StateGraph
  recall_memories  -> memory_store.recall(...)
  draft_response   -> deterministic response grounded in recalled memories
  write_memories   -> memory_store.remember(...)
      |
      v
MemantoMemoryStore or LocalJsonMemoryStore
```

The graph intentionally has no checkpointer. Durable facts live in Memanto or the local preview file, not in LangGraph state.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
copy .env.example .env
```

For live Memanto mode, edit `.env` and set `MOORCHEH_API_KEY`.

Dependency note: `requirements.txt` excludes `pyjwt==2.12.1` because that
resolved version has been flagged by OSV as `PYSEC-2025-183` in dependency
scans. This example does not decode JWTs directly; live SDK integrations should
still keep JWT dependencies updated and avoid accepting untrusted algorithms or
keys.

## Run the Demo

Offline preview, no secrets required:

```bash
python run_demo.py --backend local --mode full --reset-local
```

Live Memanto backend:

```bash
python run_demo.py --backend memanto --mode full
```

Separate-process proof:

```bash
python run_demo.py --backend local --mode learn --reset-local
python run_demo.py --backend local --mode recall
```

The recall run uses a fresh `thread_id` and a new store instance. It can only answer with the previous order and replacement preference if the memory layer persisted them.

## Reviewer Checklist

- Session one stores order `AR-8841` and the replacement-before-refund preference through `memory_store.remember(...)`.
- Session two uses `thread_id="session-two"` and a new `LocalJsonMemoryStore` instance pointed at the same memory file.
- LangGraph has no checkpointer in this example; the recalled facts can only come from Memanto or the local preview memory adapter.
- `validate_offline.py` fails if no memory file is created, if no durable memories are recalled, or if the final answer misses the stored order/preference facts.

## Validate

```bash
python validate_offline.py
python -m pytest tests -q
```

Expected result:

```text
offline validation passed
session-one stored durable order and preference memories
session-two used a fresh thread and recalled AR-8841 + replacement preference
```

## Files

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── graph.py
├── memory_store.py
├── demo.gif
├── requirements.txt
├── run_demo.py
├── validate_offline.py
└── tests/test_cross_session.py
```
