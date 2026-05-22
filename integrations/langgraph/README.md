# LangGraph + Memanto: Persistent Cross-Session Memory

This package provides [LangGraph](https://github.com/langchain-ai/langgraph) tools and a pre-built workflow for integrating [Memanto's](https://memanto.ai) persistent, cross-session memory capabilities into your LangGraph agents.

## Installation

```bash
pip install langgraph-memanto
```

## What This Demonstrates

- **Cross-session recall**: The agent remembers information from previous sessions — even when invoked in a completely new process
- **Typed semantic memory**: 13 memory types (fact, preference, decision, observation, etc.) for structured storage
- **AI-driven confidence scoring**: The agent self-evaluates certainty before storing memories
- **Contradiction detection**: Conflicting memories are flagged with versioning, not silently overwritten
- **Three primitives**: `remember`, `recall`, and `answer` — LLM-grounded responses from memory
- **Intelligent routing**: A LangGraph workflow that classifies queries and routes to the right Memanto primitive

## Architecture

```
QUERY -> CLASSIFY -> recall  -> RESPOND
                   -> remember -> RESPOND
                   -> answer   -> RESPOND
```

The workflow uses LangGraph's **conditional edges** to route queries to the appropriate Memanto primitive based on intent classification.

## Quick Start

### Option 1: Pre-built Workflow

```python
from langgraph_memanto import create_memanto_agent

agent = create_memanto_agent(agent_id="support-agent", pattern="support")

# Session 1: Store customer context
result = agent.invoke({
    "query": "Customer prefers email communication and has a billing issue",
})

# Session 2 (new process, next day): Recall
agent2 = create_memanto_agent(agent_id="support-agent")
result = agent2.invoke({
    "query": "What are this customer's preferences?",
})
```

### Option 2: Use Tools in Your Own Graph

```python
from langgraph_memanto import MemantoSetup, create_memanto_tools
from langgraph.graph import StateGraph, END

setup = MemantoSetup(api_key="moorcheh-...")
client = setup.setup(agent_id="my-agent")
tools = create_memanto_tools(client, agent_id="my-agent")

graph = StateGraph(MyState)
graph.add_node("recall", tools["recall")
graph.add_node("remember", tools["remember"])
graph.add_node("answer", tools["answer"])
```

### Option 3: Use Tools with LangChain ReAct Agent

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph_memanto import MemantoSetup, create_memanto_tools

setup = MemantoSetup(api_key="moorcheh-...")
client = setup.setup(agent_id="react-agent")
tools = create_memanto_tools(client, agent_id="react-agent")

llm = ChatOpenAI(model="gpt-4o-mini")
agent = create_react_agent(llm, list(tools.values()))
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An OpenAI or OpenRouter API key (for the LangGraph LLM)

## API Reference

### MemantoSetup

Manages Memanto agent lifecycle (create, activate session, teardown).

### create_memanto_tools(client, agent_id)

Returns a dict of three LangChain @tool functions:

| Tool | Description | Input |
|------|-------------|-------|
| `remember` | Store a typed memory | memory_type, title, content, confidence, tags |
| `recall` | Search memories by similarity | query, limit, memory_types |
| `answer` | RAG answer from memories | question |

### create_memanto_agent(...)

Full factory that returns a compiled LangGraph StateGraph.

### build_memanto_graph(llm, memanto_tools)

Build the LangGraph workflow from components.

## Memory Types

Memanto supports 13 typed semantic categories:

| Type | Use For | Example |
|------|---------|---------|
| `fact` | Objective truths/data | "API rate limit is 100 req/min" |
| `preference` | User likes/dislikes | "Customer prefers email contact" |
| `goal` | Objectives/targets | "Reduce response time to <2s" |
| `decision` | Choices made | "We chose PostgreSQL over MongoDB" |
| `observation` | Trends/patterns | "Error rate spikes at 3pm daily" |
| `instruction` | How-tos/directives | "Always verify identity before reset" |
| `commitment` | Promises/next steps | "Will send refund by Friday" |
| `context` | Background info | "Customer is on the enterprise plan" |
| `learning` | Insights/lessons | "Webhook retries need exponential backoff" |
| `event` | Occurrences/meetings | "Deployment call scheduled for 3pm" |
| `artifact` | Files/code/deliverables | "Config file at /etc/app/conf.yaml" |
| `relationship` | Entity connections | "Alice reports to Bob in engineering" |
| `error` | Failures/mistakes | "Forgot to check null before accessing field" |

## Comparison with CrewAI Integration

| Feature | LangGraph | CrewAI |
|---------|-----------|--------|
| Integration package | langgraph-memanto | crewai-memanto |
| Tools | LangChain @tool | CrewAI BaseTool |
| Workflow | StateGraph with conditional edges | Crew pipeline |
| Query routing | Automatic (LLM-based classification) | Manual (agent assignment) |
| Cross-session recall | Yes | Yes |
| RAG answer | Yes | Yes |
| Contradiction detection | Yes (Memanto built-in) | Yes (Memanto built-in) |

## License

MIT
