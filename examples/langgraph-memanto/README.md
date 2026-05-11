# LangGraph + Memanto: Cross-Session Recall

This example shows a LangGraph agent using Memanto as its long-term memory
layer. The graph runs in two simulated sessions:

1. Session 1 stores user preferences and support context in Memanto.
2. Session 2 starts with an empty LangGraph state and recalls those memories
   from Memanto before generating a response.

The important point is that the remembered facts are not passed through
LangGraph state. They live outside the graph in Memanto and are retrieved in a
later session.

## What It Demonstrates

- Cross-session recall with fresh LangGraph state.
- Memanto as an external memory layer, not a state checkpoint.
- Typed memories for preference, fact, and goal records.
- A deterministic demo that can run without an LLM key.
- A local fallback store for quick review when `MOORCHEH_API_KEY` is not set.

## Install

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install -r examples/langgraph-memanto/requirements.txt
```

On macOS/Linux, use `source .venv/bin/activate`.

## Run With Memanto

Set your Moorcheh key, then run the demo:

```bash
set MOORCHEH_API_KEY=your_key_here
python examples/langgraph-memanto/run_demo.py
```

On macOS/Linux:

```bash
export MOORCHEH_API_KEY=your_key_here
python examples/langgraph-memanto/run_demo.py
```

The script creates or reuses the `langgraph-customer-success-demo` Memanto
agent, stores memories in one session, then creates a new graph state and
recalls them in another session.

## Run In Local Review Mode

If `MOORCHEH_API_KEY` is missing, the example automatically uses a small local
JSON memory store at `.local_memanto_review_store.json`. This keeps the graph
easy to review while preserving the same `remember`, `recall`, and `answer`
interface used by the real Memanto-backed adapter.

```bash
python examples/langgraph-memanto/run_demo.py
```

## Expected Output

The second session should answer with details from the first session, including:

- the customer prefers concise updates,
- the customer is on the Pro plan,
- the current goal is resolving invoice export errors.

Those facts are not present in the second session's initial graph state.

## Files

- `run_demo.py` - LangGraph workflow and demo runner.
- `memanto_memory.py` - Memanto adapter plus local review fallback.
- `requirements.txt` - Extra dependencies for this example.
