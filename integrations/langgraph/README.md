# LangGraph + Memanto: Persistent Long-Term Memory for Stateful Agents

[Memanto](https://memanto.ai) is a **memory agent** — typed semantic memory with confidence,
provenance, and zero-ingestion-latency retrieval. This package integrates Memanto as a
`Store` backend for [LangGraph](https://langchain-ai.github.io/langgraph/) agents, giving
them persistent, cross‑session, cross‑agent memory with sub‑90 ms recall.

## What you get

- **`MemantoStore`** — a drop‑in replacement for LangGraph's `InMemoryStore` or `BaseStore`
  that persists all data in a Memanto namespace.
- **Memory tools** for LangGraph agents — `remember`, `recall`, `answer`, `batch_remember` —
  so your graph can explicitly read/write memory without extra API calls.
- **Automatic session management** — sessions are activated on first use and automatically
  renewed before expiry.

## Installation

```bash
pip install langgraph-memanto
```

Requires Python 3.10+, a [Moorcheh API key](https://console.moorcheh.ai/api-keys)
(free tier: 100K ops/month), and `langgraph>=0.2.0`.

## Quick Start

### 1. Set up the MemantoStore

```python
import os
from langgraph_memanto import MemantoStore

store = MemantoStore(
    api_key=os.getenv("MOORCHEH_API_KEY"),
    agent_id="my-lg-agent",
    auto_create=True,
)
```

### 2. Attach it to your StateGraph

```python
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

# ... define your state, nodes, edges ...
graph = StateGraph(MyState)
# ... compile with store
app = graph.compile(
    checkpointer=MemorySaver(),
    store=store,
)
```

Now the graph's `memory_store` (e.g. via `config["store"]`) will use Memanto.

### 3. Use the memory tools inside your nodes

```python
from langgraph_memanto import create_memanto_tools

tools = create_memanto_tools(agent_id="my-lg-agent", api_key=os.getenv("MOORCHEH_API_KEY"))

# Inside a LangGraph node:
def research_node(state):
    # Store a research finding
    tools["remember"]("The company has 500 employees")
    # Recall previous decisions
    results = tools["recall"]("What do we know about the company size?")
    return {"context": results}
```

## Advanced Usage

### Custom memory types, tags, and confidence

```python
tools["remember"](
    memory="User prefers dark mode",
    memory_type="preference",
    tags=["ui", "theme"],
    confidence=0.95,
    provenance="explicit_statement",
)
```

### Batch storing

```python
tools["batch_remember"]([
    {"memory": "Alice is the CEO", "memory_type": "fact"},
    {"memory": "Goal: reach 10k users", "memory_type": "goal"},
])
```

### Using `MemantoStore` directly (without tools)

The store implements `BaseStore` so you can use `store.get(namespace, key)` and
`store.put(namespace, key, value)`.

```python
await store.aput(("users", "alice"), "preferences", {"theme": "dark"})
result = await store.aget(("users", "alice"), "preferences")
```

## How it works

```
┌──────────────┐     LangGraph     ┌──────────────────┐    Moorcheh API    ┌─────────────┐
│ LangGraph    │ ◄───────────────► │  langgraph-store │ ────────────────► │   Moorcheh  │
│   Agent      │   store.get/put  │  (this package)  │ ◄──────────────── │   Service   │
└──────────────┘                   └──────────────────┘    HTTPS+API key   └─────────────┘
                                           │
                                           └─ uses memanto.cli.client.SdkClient
                                              (same client the Memanto CLI uses)
```

- On first use, the store ensures the Memanto agent exists and activates a JWT
  session. Sessions auto‑renew.
- `get` maps to Memanto's `recall` with exact item lookup.
- `put` maps to Memanto's `remember`.
- For bulk operations, it batches under the hood.

## Configuration

All configuration is via environment variables or keyword arguments.

| Variable / Arg | Required | Default | Description |
|----------------|----------|---------|-------------|
| `MOORCHEH_API_KEY` | **yes** | — | Moorcheh API key. |
| `agent_id` | recommended | `None` (falls back to `MEMANTO_DEFAULT_AGENT_ID` env var, then `"langgraph-agent"`) | Memanto agent ID (namespace). |
| `auto_create` | no | `True` | Automatically create the agent if it doesn't exist. |
| `pattern` | no | `tool` | Agent pattern (`support`/`project`/`tool`). |
| `session_duration_hours` | no | server default (6) | Session lifetime. |

## Relationship to Other Integrations

Memory written by the LangGraph integration can be retrieved by the
[MCP server](https://github.com/moorcheh-ai/memanto/tree/main/integrations/mcp) or
[CrewAI tools](https://github.com/moorcheh-ai/memanto/tree/main/integrations/crewai)
when they share the same `agent_id`.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — same as the [Memanto](https://github.com/moorcheh-ai/memanto) project.
