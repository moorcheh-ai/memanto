# LangGraph + Memanto: Long-Term Memory for Stateful Agents

This example demonstrates using Memanto as the long-term memory layer for a LangGraph agent. The agent can remember facts across conversation turns and recall them when relevant.

## How It Works

1. **User input** → LangGraph agent processes it
2. **Memanto remember** → Agent stores important facts as memory records
3. **Memanto recall** → Agent retrieves relevant memories for context
4. **Memanto answer** → Agent answers from stored knowledge

## Prerequisites

```bash
pip install memanto langgraph langchain-openai
export MEMANTO_API_KEY=your_key_here
export OPENAI_API_KEY=your_key_here
```

## Usage

```bash
python examples/langgraph-memory/memory_agent.py
```
