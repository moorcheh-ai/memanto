# LangGraph + Memanto Cross-Session Support Agent

This example shows a LangGraph customer-support workflow using Memanto as a long-term memory layer outside the graph state.

It demonstrates the bounty requirement directly:

- Session 1 stores durable customer facts and decisions.
- Session 2 starts fresh, asks a new support question, and recalls yesterday's facts from memory.
- The LangGraph workflow injects recalled context into the response and stores any new preference learned during the run.

![Cross-session recall demo](assets/demo.gif)

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- assets/demo.gif
|-- customer_support_graph.py
|-- make_demo_gif.py
|-- memory_backends.py
|-- requirements.txt
`-- run_cross_session_demo.py
```

## Quick Start

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Runs without external keys by using the local JSON memory backend.
python run_cross_session_demo.py --backend file --reset
```

## Run With Memanto

Install and configure Memanto first:

```bash
pip install memanto
memanto
```

Then run the same graph against the real Memanto CLI backend:

```bash
python run_cross_session_demo.py --backend memanto --agent-id langgraph-support-demo
```

The graph stores and recalls memories with normal Memanto CLI commands:

```bash
memanto remember "Customer Alex prefers email follow-ups." --type preference
memanto recall "How should we follow up with Alex?"
```

## What The Graph Does

The graph has three nodes:

1. `recall_memory`: searches Memanto for account facts relevant to the user's current question.
2. `compose_response`: writes a grounded support response using the recalled memories.
3. `store_followup_learning`: persists a new preference if the latest message contains one.

Memanto remains the durable memory source. LangGraph only carries the current run state, so the second invocation proves cross-session recall instead of relying on an in-memory Python object.

## Verification

The file backend is included so reviewers can run the example without a Moorcheh API key. It mirrors the Memanto backend interface and writes JSON memory records to `.demo_memory.json`.

Regenerate the 30-second GIF:

```bash
python make_demo_gif.py
```

Run the demo:

```bash
python run_cross_session_demo.py --backend file --reset
```

Expected output includes:

```text
Recalled memories:
- Customer Alex is on the enterprise plan.
- Customer Alex prefers email follow-ups before demos.
- Invoices for Alex should stay in GBP.
```

Run the focused offline tests:

```bash
python -m unittest discover -s examples/langgraph-memanto/tests -v
```
