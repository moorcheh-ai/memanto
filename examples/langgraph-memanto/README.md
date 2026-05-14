# LangGraph + MEMANTO: The Permanent Brain Integration

This example demonstrates how to give your LangGraph agents a **Permanent Brain** using MEMANTO.

While LangGraph's standard state management (checkpointers) is excellent for short-term thread memory, it doesn't natively handle **cross-session recall** or **long-term memory synthesis** out of the box. This integration bridges that gap.

## Features

1.  **MemantoSaver**: A custom `BaseCheckpointSaver` that stores the graph's state directly in Memanto's semantic storage.
2.  **Cross-Session Tools**: Specialized tools (`memanto_remember`, `memanto_recall`, `memanto_answer`) that allow agents to explicitly manage their long-term knowledge base.
3.  **Semantic Search**: Unlike key-value checkpointers, Memanto allows the agent to find relevant context using natural language queries.

## Architecture

![Architecture](https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png)

- **LangGraph**: Orchestrates the agent's logic and short-term state.
- **MEMANTO**: Acts as the long-term storage and semantic retrieval layer.
- **Moorcheh.ai**: Provides the underlying no-indexing semantic database.

## Prerequisites

- Python 3.9+
- `langgraph`, `langchain-openai`
- `MOORCHEH_API_KEY` (Get one for free at [moorcheh.ai](https://moorcheh.ai))

## Installation

```bash
pip install langgraph langchain-openai memanto
```

## Running the Example

1. Set your API keys:
   ```bash
   export MOORCHEH_API_KEY="mk_your_key"
   export OPENAI_API_KEY="sk-your-key"
   ```

2. Run the agent:
   ```bash
   python agent.py
   ```

## How it Works

The agent in `agent.py` uses two layers of memory:

1.  **Transactional Memory (Checkpointer)**: `MemantoSaver` saves the exact state of the graph. If the process crashes or the thread is resumed, the agent picks up exactly where it left off.
2.  **Semantic Memory (Tools)**: The agent uses `memanto_remember` to store facts it deems important (e.g., "User prefers technical explanations"). In a **new thread**, it uses `memanto_recall` to retrieve these facts, even though the transactional state is empty.

This combination allows for agents that are both statefully robust and long-term intelligent.
