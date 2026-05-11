# LangGraph + Memanto: Cross-Session Agent Memory

This example shows a LangGraph support agent using **Memanto** as its
long-term memory layer. LangGraph manages the current turn state, while
Memanto stores durable memories that survive across separate Python
processes and separate graph invocations.

## What This Demonstrates

- **Cross-session recall**: `run_day2_recall.py` starts with an empty graph
  state but remembers facts stored by `run_day1_store.py`.
- **Memory outside LangGraph state**: durable customer preferences live in
  Memanto, not in the `SupportState` object.
- **Typed semantic memory**: preferences, facts, and events are stored with
  Memanto memory types, confidence scores, and tags.
- **Minimal LangGraph wiring**: a small `StateGraph` keeps the example focused
  on the integration pattern.
- **No external LLM key required**: the graph uses deterministic nodes so the
  memory behavior is easy to inspect and record.

## Architecture

```text
Session 1                         Persistent Memory              Session 2
---------                         -----------------              ---------
LangGraph state                   Memanto namespace              New LangGraph state
  incoming message  ----remember-> customer facts/preferences
  generated reply                                                 incoming message
                                                                  recall ---->
                                                                  personalized reply
```

The graph uses one shared Memanto agent ID, `langgraph-support-agent` by
default. You can override it with `MEMANTO_AGENT_ID` to isolate your own demo
runs.

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys)

## Setup

```bash
git clone https://github.com/moorcheh-ai/memanto.git
cd memanto/examples/langgraph-memanto

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and add MOORCHEH_API_KEY
```

## Quick Start

Run both sessions:

```bash
python run_full_demo.py
```

Or run them separately to make the persistence boundary obvious:

```bash
python run_day1_store.py

# Later, in a fresh terminal or after clearing local LangGraph state:
python run_day2_recall.py
```

Expected behavior:

1. Day 1 stores stable customer details such as name, plan, timezone, and
   escalation preference.
2. Day 2 starts with no prior LangGraph messages, recalls those details from
   Memanto, and answers with personalized context.

## No-Key Dry Run

The bounty demo should use real Memanto storage. For reviewers who only want
to inspect the graph flow without an API key, the same scripts can use a local
JSON backend:

```bash
MEMANTO_DEMO_BACKEND=local python run_full_demo.py
```

The local backend writes `.local_memanto_demo.json` in this folder and exposes
the same small interface used by the LangGraph nodes.

## Files

```text
examples/langgraph-memanto/
|-- README.md              # This guide
|-- requirements.txt       # Python dependencies
|-- .env.example           # Configuration template
|-- memory_adapter.py      # Memanto client wrapper + optional local backend
|-- graph.py               # LangGraph StateGraph and node functions
|-- run_day1_store.py      # Session 1: store memories
|-- run_day2_recall.py     # Session 2: recall from an empty graph state
`-- run_full_demo.py       # Runs both sessions in sequence
```

## How to Record the 30-Second Demo

Suggested terminal flow:

```bash
python run_day1_store.py
python run_day2_recall.py
```

The recording should show that the second script starts a new run and still
recalls the customer's stored preferences. Add your GIF or video URL here when
submitting the PR:

Demo video: TODO

## Integration Pattern

LangGraph state is intentionally short-lived:

```python
class SupportState(TypedDict):
    customer_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    memories_to_store: list[dict[str, Any]]
```

Memanto is injected as a dependency when building the graph:

```python
memory = create_memory_backend()
graph = build_support_graph(memory)
result = graph.invoke({"customer_id": "acme-001", "message": "..."})
```

This separation keeps LangGraph responsible for orchestration while Memanto
owns durable semantic memory.
