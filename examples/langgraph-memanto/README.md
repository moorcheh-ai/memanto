# LangGraph + Memanto Cross-Session Memory Demo

This example shows Memanto acting as the long-term memory layer for a
LangGraph customer support workflow.

The graph itself is intentionally simple and deterministic: it does not need an
LLM key. Session 1 stores Jamie's support preference in Memanto. Session 2 starts
with a fresh LangGraph state, recalls that preference from Memanto, and uses it
to draft the next support response.

![30-second demo GIF](assets/demo.gif)

## What This Demonstrates

- Cross-session recall: the second graph run remembers something from
  "yesterday" that is not present in the current LangGraph state.
- Memanto outside graph state: persistent `remember` and `recall` calls happen
  in graph nodes, while the LangGraph state only carries current-session data.
- Clean support-agent pattern: the same structure can be replaced with an LLM
  node later, but the memory boundary stays the same.

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- run_demo.py
`-- assets/demo.gif
```

## Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r examples/langgraph-memanto/requirements.txt
cp examples/langgraph-memanto/.env.example examples/langgraph-memanto/.env
```

Edit `examples/langgraph-memanto/.env` and add your Moorcheh API key:

```bash
MOORCHEH_API_KEY=...
```

## Run the Real Memanto Demo

```bash
cd examples/langgraph-memanto
python run_demo.py
```

Expected flow:

1. `Session 1 - yesterday` starts with no recalled memories.
2. The graph stores Jamie's preference for quick refunds in Memanto.
3. `Session 2 - today` starts with a fresh LangGraph state.
4. The graph recalls Jamie's refund preference from Memanto.
5. The response recommends checking refund eligibility first.

## Local Smoke Test Without an API Key

Use dry-run mode to verify the LangGraph flow locally:

```bash
cd examples/langgraph-memanto
python run_demo.py --dry-run
```

Dry-run mode uses the same graph nodes with an in-memory stand-in. It is only
for smoke testing; the real bounty demo should be run without `--dry-run`.

## Why Memanto Belongs Outside LangGraph State

LangGraph state is great for one execution thread, but long-term memory should
survive separate runs, restarts, and disjoint sessions. This example keeps the
graph state small:

```python
{
    "session_label": "...",
    "user_id": "jamie",
    "message": "...",
    "recalled_memories": [],
    "stored_memory_ids": [],
}
```

The state never carries yesterday's preference directly into today's run.
Instead, the `recall_customer_context` node asks Memanto for relevant support
memories at the beginning of each run.
