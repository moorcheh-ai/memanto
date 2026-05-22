# LangGraph + Memanto Example

This example shows how to give a LangGraph workflow durable memory with
Memanto. The graph recalls relevant memories before an agent node runs, injects
them into state as `memanto_context`, then stores explicit facts, preferences,
decisions, and learnings emitted by later nodes.

## What This Demonstrates

- Cross-session recall for LangGraph agents.
- A reusable `MemantoGraphMemory` adapter with `recall_node`, `remember_node`,
  and `wrap_node`.
- A credential-free local JSONL backend for review and tests.
- A live `memanto` CLI backend for real Moorcheh-backed memory.
- Secret redaction and duplicate prevention before memories are stored.
- A 30-second GIF showing the two-session memory flow.

## 30-Second Demo

![LangGraph + Memanto 30-second demo](assets/langgraph-memanto-demo.gif)

## Quick Demo

The default demo uses a local JSONL file so it works without API keys:

```bash
cd examples/langgraph-memanto
python demo.py
```

To run the same graph against real Memanto memory:

```bash
pip install -r requirements.txt
memanto agent create langgraph-memanto-demo
MEMANTO_LANGGRAPH_BACKEND=cli python demo.py
```

On Windows PowerShell:

```powershell
$env:MEMANTO_LANGGRAPH_BACKEND="cli"
python demo.py
```

## LangGraph Wiring

```python
from langgraph.graph import END, START, StateGraph

from langgraph_memanto import JsonlMemoryBackend, MemantoGraphMemory

backend = JsonlMemoryBackend(".memanto-langgraph-demo/memory.jsonl")
memory = MemantoGraphMemory(backend=backend, recall_limit=5)

def assistant_node(state):
    # Put this into your LLM system prompt or tool-planning context.
    durable_context = state.get("memanto_context", "")
    return {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "Decision: Use Stripe Checkout for the first payment milestone."
                ),
            }
        ]
    }

builder = StateGraph(dict)
builder.add_node("recall_memory", memory.recall_node)
builder.add_node("assistant", assistant_node)
builder.add_node("remember_memory", memory.remember_node)

builder.add_edge(START, "recall_memory")
builder.add_edge("recall_memory", "assistant")
builder.add_edge("assistant", "remember_memory")
builder.add_edge("remember_memory", END)

graph = builder.compile()
graph.invoke({"messages": [{"role": "user", "content": "Plan checkout"}]})
```

For an existing node, use the wrapper:

```python
builder.add_node("assistant", memory.wrap_node(assistant_node, node_name="assistant"))
```

## Memory Contract

The adapter stores explicit memories from:

- State keys such as `remember`, `facts`, `preferences`, `decisions`,
  `learnings`, and `instructions`.
- Marked lines in node messages such as `Decision: ...`, `Preference: ...`,
  `Fact: ...`, and `Remember: ...`.

Each stored memory is normalized into Memanto's memory types and tagged with
`langgraph`. The local backend keeps data in JSONL so tests can prove
persistence across new graph sessions. The CLI backend maps the same calls to:

```bash
memanto remember "..." --type decision --source assistant
memanto recall "checkout payment plan" --limit 5
```

## Files

```text
examples/langgraph-memanto/
|-- assets/
|   `-- langgraph-memanto-demo.gif
|-- README.md
|-- demo.py
|-- demo_transcript.md
|-- langgraph_memanto.py
|-- requirements.txt
`-- tests/
    `-- test_langgraph_memanto.py
```

## Verification

```bash
python -m py_compile langgraph_memanto.py demo.py tests/test_langgraph_memanto.py
python -m unittest discover -s tests
```

The demo transcript in `demo_transcript.md` shows the two-session flow: the
first graph run stores a payment decision, and the second run recalls it before
answering.
