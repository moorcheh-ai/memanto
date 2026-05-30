# Memanto + LangGraph: Cross-Session Long-Term Memory

> Solves **Memory Fragmentation** across LangGraph agent sessions by making Memanto a persistent, cross-session memory layer.

## Problem

When using LangGraph agents across different conversation threads, each session starts with a blank slate. Decisions made in one session are invisible to the next. You end up re-prompting the same preferences, re-stating the same conventions, and re-explaining the same decisions across every thread.

## Solution

This integration adds a **transparent memory layer** across LangGraph agent executions:

1. **Recall Node (Pre-LLM):** Before the agent processes input, relevant memories are recalled from Memanto and injected into the LLM context.
2. **Store Node (Post-LLM):** After the agent produces output, engineering signals are extracted and stored for future sessions.
3. **Cross-Session Recall:** Different conversation threads share memory through the same Memanto backend.

## Quick Start

### Credential-Free Mode (Reviewer Safe)

```bash
python3 validate.py
python3 -m pytest test_langgraph_integration.py -v
```

### Production Mode (with Moorcheh API Key)

```bash
export MOORCHEH_API_KEY="your-api-key"
python3 -c "from graph_builder import invoke_graph; print(invoke_graph('Hello'))"
```

### Basic Usage

```python
from graph_builder import invoke_graph
from memory_backend import LocalBackend

# Create a backend (uses LocalBackend by default, MemantoBackend if MOORCHEH_API_KEY is set)
backend = LocalBackend(data_dir="/tmp/my-agent-memory")

# Run the memory-enhanced graph
result = invoke_graph(
    "We decided to use event sourcing for the order system",
    session_id="session-1",
    stage="planning",
    backend=backend,
)

# In a different session, memories are automatically recalled
result2 = invoke_graph(
    "What architecture did we choose for orders?",
    session_id="session-2",
    backend=backend,
)
# result2["recalled_memories"] contains memories from session-1!
```

### Using Hooks (for existing workflows)

```python
from hooks import pre_execution_hook, post_execution_hook
from memory_backend import LocalBackend

backend = LocalBackend(data_dir="/tmp/my-agent-memory")

# Before your LLM call
context = pre_execution_hook("Design the order system", session_id="s1", backend=backend)
# Inject context into your LLM system prompt

# After your LLM call
memory_ids = post_execution_hook("Design the order system", llm_output, session_id="s1", backend=backend)
```

### Building a Custom Graph

```python
from langgraph.graph import END, StateGraph
from memory_nodes import recall_memories, store_memories
from memory_backend import LocalBackend

def my_agent(state):
    # Your custom LLM logic here
    # state["memory_context"] contains recalled memories
    return {**state, "messages": state["messages"] + [{"role": "assistant", "content": "response"}]}

graph = StateGraph(dict)
graph.add_node("recall", recall_memories)
graph.add_node("agent", my_agent)
graph.add_node("store", store_memories)

graph.set_entry_point("recall")
graph.add_edge("recall", "agent")
graph.add_edge("agent", "store")
graph.add_edge("store", END)

compiled = graph.compile()
result = compiled.invoke({
    "messages": [{"role": "user", "content": "Hello"}],
    "session_id": "my-session",
    "backend": LocalBackend(),
    "stage": None,
    "memory_context": "",
    "recalled_memories": [],
    "stored_memory_ids": [],
})
```

## Files

| File | Purpose |
|------|---------|
| `memory_backend.py` | Protocol-based backend (Local JSONL + Memanto SDK) |
| `memory_nodes.py` | LangGraph node functions: recall_memories + store_memories |
| `graph_builder.py` | Build the LangGraph StateGraph with memory nodes |
| `hooks.py` | Pre/post execution hooks for memory injection |
| `validate.py` | Credential-free validation script |
| `test_langgraph_integration.py` | Comprehensive test suite |
| `README.md` | This file |

## How It Works

### Signal Extraction

The store_memories node scans LLM I/O for engineering signals:

| Pattern | Memory Type | Confidence |
|---------|-------------|------------|
| must/always/shall/never X | instruction | 0.90 |
| decided/chose/agreed to X | decision | 0.85 |
| prefer/favor/standard is X | preference | 0.75 |
| pattern/convention/approach is X | decision | 0.80 |
| TODO/FIXME/NOTE/IMPORTANT X | context | 0.60 |

### Memory Injection

The recall_memories node formats recalled memories:

```text
## Memory Context (from Memanto)
The following are your established decisions, instructions, and preferences from previous sessions. Honor them.

- [DECISION] Use event sourcing for orders [architecture] (confidence: 85%)
- [INSTRUCTION] Must always use aggregate roots [tdd, implementation] (confidence: 90%)
```

### Graph Topology

```text
┌─────────────────┐     ┌──────────┐     ┌────────────────┐
│ recall_memories  │────▶│  agent   │────▶│ store_memories  │──▶ END
└─────────────────┘     └──────────┘     └────────────────┘
       │                                      │
       │ Recall from Memanto                  │ Store to Memanto
       ▼                                      ▼
  ┌──────────┐                          ┌──────────┐
  │  Memanto  │                          │  Memanto  │
  │  Backend  │                          │  Backend  │
  └──────────┘                          └──────────┘
```

### Cross-Session Flow

```text
Session 1: "We decided to use event sourcing for orders"
  store_memories: Stores DECISION memory

Session 2: "What architecture should we use?"
  recall_memories: Recalls "Use event sourcing for orders"
  Agent sees established architecture decision

Session 3: "Implement the Order aggregate"
  recall_memories: Recalls "event sourcing" + "aggregate roots"
  No re-prompting needed!
```

## Key Differentiators

1. **LangGraph native nodes** — recall_memories and store_memories as proper graph nodes
2. **Protocol-based backend** — LocalBackend (credential-free) + MemantoBackend (live SDK)
3. **Cross-session recall** — Different threads share memory through the same backend
4. **Weighted signal extraction** — Calibrated confidence scores per signal type
5. **Stage-aware tag boosting** — Domain-specific tags for each workflow stage
6. **Hooks for non-graph workflows** — Pre/post hooks for simpler integrations
7. **Full lifecycle coverage** — Graph nodes + standalone hooks + file-reference capture

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MOORCHEH_API_KEY | (none) | When set, uses live SDK backend |
| MEMANTO_AGENT_ID | langgraph-memory-companion | Agent ID for SDK |
| MEMANTO_LANGGRAPH_DATA | ~/.memanto/langgraph-memory | Local backend data dir |

## References

- Bounty issue: [#397](https://github.com/moorcheh-ai/memanto/issues/397)
- LangGraph: <https://github.com/langchain-ai/langgraph>
- Moorcheh API: <https://moorcheh.ai>
