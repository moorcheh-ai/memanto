# LangGraph + Memanto: Long-Term Memory for Stateful Agents

This example demonstrates Memanto as the **persistent memory layer** for a LangGraph-based customer support agent.

## How It Works

```
Customer Query → Analyze Intent → Recall Memanto Memories → Generate Response → Store New Memories
```

1. **Analyze Query**: Determines intent (billing, technical, account, order, general) and sentiment
2. **Recall Memories**: Queries Memanto for past interactions with this customer
3. **Generate Response**: Creates personalized response using recalled context
4. **Store Memories**: Summarizes and persists the interaction into Memanto for future use

## Key Features

- **Cross-session memory**: Memanto stores memories that persist across LangGraph sessions
- **Personalized responses**: The agent recalls past issues, preferences, and resolutions
- **Automatic distillation**: Each interaction is summarized and stored with metadata
- **Multi-customer support**: Each customer has their own memory namespace

## Usage

```bash
export MEMANTO_API_KEY="your-api-key"
export MEMANTO_BRAIN_ID="customer-support-brain"

python examples/langgraph-memanto/customer_support_agent.py
```

## Why Memanto?

LangGraph's built-in `MemorySaver` handles **short-term** conversation state. Memanto provides the **long-term** memory layer that persists across threads, sessions, and even different agent topologies — making it the perfect complement for production LangGraph deployments.

## Video / Demo

Run the demo script and record:
```bash
python examples/langgraph-memanto/customer_support_agent.py
```
