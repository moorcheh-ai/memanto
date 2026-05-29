# LangGraph + Memanto: Persistent Semantic Memory for Stateful Agent Graphs

This package integrates [Memanto](https://memanto.ai) as a long-term memory layer for [LangGraph](https://langchain-ai.github.io/langgraph/) agent graphs. Memanto provides typed semantic memory with confidence, provenance, and sub-90ms retrieval — enabling your LangGraph agents to remember across sessions, manage contradictions, and share knowledge.

## Installation

```bash
pip install langgraph-memanto
```

Requires Python 3.10+ and a [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month).

## How It Works

LangGraph agents operate on a `State` object. Memanto memory lives outside the graph — any node can invoke `remember`, `recall`, or `answer` tools to persist or retrieve information. Memory persists across graph runs, agent restarts, and even across different LangGraph agents sharing the same Memanto agent ID.

## Quick Start

### 1. Configure your API key

Set the `MOORCHEH_API_KEY` environment variable:

```bash
export MOORCHEH_API_KEY="mch_xxxxxxxxxxxxxxxxxx"
```

### 2. Create Memanto tools and bind to a graph

```python
from langgraph.prebuilt import create_react_agent
from langgraph_memanto import create_memanto_tools

# Create a Memanto client and retrieve LangChain tools
tools = create_memanto_tools(
    api_key="your-key",  # or omit to use MOORCHEH_API_KEY env var
    agent_id="my-langgraph-agent",   # memory namespace
)

# Use them in a LangGraph agent (e.g., prebuilt ReAct agent)
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI  # or any other LLM

model = ChatOpenAI(model="gpt-4")
graph = create_react_agent(model, tools, state_modifier="You have access to long-term memory tools. Use them to remember user preferences and recall past decisions.")

# Run the graph
for chunk in graph.stream({"messages": [("human", "Remember that I prefer dark mode")]}):
    pass  # process stream

# In a new session
for chunk in graph.stream({"messages": [("human", "What display mode do I prefer?")]}):
    pass  # agent will recall the stored preference
```

> **Note**: The tools use a shared Memanto agent namespace. Any LangGraph agent, regardless of session or restart, can access memories persisted by others using the same `agent_id`.

## Available Tools

The tools returned by `create_memanto_tools()` are standard LangChain `Tool` objects:

| Tool | Description |
|------|-------------|
| `memanto_remember` | Store a fact, preference, decision, goal, or instruction into long-term memory. Accepts `memory` (text), optional `memory_type` and `confidence`. |
| `memanto_recall` | Search memory by semantic similarity. Returns the most relevant memories. |
| `memanto_answer` | Generate a grounded answer using only stored memories (RAG). |
| `memanto_recall_recent` | Fetch the `n` most recent memories without a query. |
| `memanto_recall_as_of` | Point-in-time recall: what was known on a specific date. |
| `memanto_recall_changed_since` | Differential recall: what has changed since a given datetime. |

### Supported Memory Types

`fact`, `preference`, `goal`, `decision`, `artifact`, `learning`, `event`, `instruction`, `relationship`, `context`, `observation`, `commitment`, `error`.

## Advanced Usage: Custom Graph Nodes

For full control, you can use the `MemantoClient` directly in your custom nodes:

```python
from langgraph.graph import StateGraph
from langgraph_memanto import MemantoClient

client = MemantoClient(agent_id="custom-agent")

def remember_node(state):
    last_message = state["messages"][-1].content
    response = client.remember(
        memory=last_message,
        memory_type="observation"
    )
    return state
```

## Configuration

The `create_memanto_tools()` function accepts:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | `None` (reads `MOORCHEH_API_KEY` env) | Moorcheh API key |
| `agent_id` | `"langgraph-default"` | Memanto agent ID (memory namespace) |
| `agent_pattern` | `"tool"` | Pattern used when auto-creating the agent (`support`, `project`, `tool`) |
| `agent_auto_create` | `True` | Create agent if it doesn't exist |
| `session_duration_hours` | `6` | JWT session lifetime |

## Persistence Example: Across Restarts

Run the following script twice to prove cross-session memory:

```python
# run.py
import os
from langgraph_memanto import create_memanto_tools
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

tools = create_memanto_tools(agent_id="demo-agent")
model = ChatOpenAI(model="gpt-4")
graph = create_react_agent(model, tools)

for chunk in graph.stream({"messages": [("human",
    "Remember that my favorite color is blue.")]}):
    pass
```

First run stores the fact. Second run can query "What is my favorite color?" and the agent will recall the memory even though the script starts a new process.

## Examples

See the `examples/` directory for runnable scripts demonstrating:
- Basic memory persistence
- Cross-agent memory sharing
- Contradiction detection

## How It Differs from Other Integrations

| Integration | Interface | Best for |
|------------|-----------|----------|
| **MCP** | Model Context Protocol tools | Any MCP client (Claude, Cursor, etc.) |
| **CrewAI** | CrewAI tools | Multi-agent CrewAI pipelines |
| **LangGraph** | LangChain tools + direct client | Custom LangGraph agent graphs |

All share the same Memanto backend — memory written by one integration is recallable from another when they use the same `agent_id`.

## Support

- [Memanto Documentation](https://docs.memanto.ai)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
