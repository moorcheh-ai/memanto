# LangGraph + Memanto: Persistent Cross-Session Memory

This package provides [LangGraph](https://github.com/langchain-ai/langgraph) tools and helpers for integrating [Memanto's](https://memanto.ai) persistent, cross-session memory into your LangGraph agents.

## Installation

```bash
pip install memanto-langgraph
```

## Quick Start

```python
from memanto_langgraph import MemantoSetup, create_memanto_tools, MemantoMemorySaver

# 1. Set up Memanto agent + session
setup = MemantoSetup(api_key="your-moorcheh-api-key")
client = setup.setup(agent_id="my-langgraph-agent")

# 2. Create LangGraph-compatible tools
tools = create_memanto_tools(client, agent_id="my-langgraph-agent")

# 3. Bind tools to your LLM and build your graph
llm_with_tools = your_llm.bind_tools(tools)

# 4. Use the memory saver for automatic cross-session context
saver = MemantoMemorySaver(client, agent_id="my-langgraph-agent")
context = saver.load_context()  # Inject into system prompt
```

## What This Provides

### Tools (`create_memanto_tools`)

Three `StructuredTool` instances that your LangGraph agent can call:

| Tool | Purpose |
|------|---------|
| `memanto_remember` | Store a structured memory (fact, preference, goal, etc.) |
| `memanto_recall` | Search memories by natural-language query |
| `memanto_answer` | Get a RAG answer grounded in stored memories |

### Memory Saver (`MemantoMemorySaver`)

A helper that automatically loads relevant memories at session start and saves interactions after each turn — giving every node persistent cross-session context without requiring explicit tool calls.

```python
saver = MemantoMemorySaver(client, agent_id="my-agent")

# Before graph invocation
context = saver.load_context(query="user preferences")

# After graph invocation
saver.save_interaction(user_message="...", assistant_reply="...")
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                LangGraph Agent                   │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Node A  │→ │  Node B  │→ │  Node C  │       │
│  └──────────┘  └──────────┘  └──────────┘       │
│        │             │             │              │
│        ▼             ▼             ▼              │
│  ┌──────────────────────────────────────┐        │
│  │      Memanto Tools (bound to LLM)    │        │
│  │  remember │ recall │ answer           │        │
│  └──────────────┬───────────────────────┘        │
│                 │                                 │
│  ┌──────────────┴───────────────────────┐        │
│  │      MemantoMemorySaver               │        │
│  │  load_context() │ save_interaction()  │        │
│  └──────────────┬───────────────────────┘        │
└─────────────────┼────────────────────────────────┘
                  │
                  ▼
         ┌─────────────────┐
         │    Memanto       │
         │  (Persistent     │
         │   Memory DB)     │
         └─────────────────┘
```

## Example: Research Assistant

See the full working example in [`examples/langgraph-memanto`](../../examples/langgraph-memanto/).

## Requirements

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys)
- An LLM API key (OpenAI, Anthropic, etc.)

## License

MIT
