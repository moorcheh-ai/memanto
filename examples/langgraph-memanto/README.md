# LangGraph + Memanto: Persistent Cross-Session Memory

This example demonstrates how to give a LangGraph agent a permanent brain
using [Memanto](https://memanto.ai) – a memory agent that remembers,
recalls, and answers across completely separate sessions.

## Why This Matters

LangGraph agents are stateful within a single session, but their state
evaporates when the session ends. With Memanto, your agent can:

- **Remember** user preferences, facts, and decisions permanently
- **Recall** past interactions when a user returns days later
- **Answer** complex questions grounded in accumulated knowledge

No more "Hi, who are you?" on every new conversation.

## Quick Start

### 1. Get API Keys

```bash
# Memanto (free tier available)
export MEMANTO_API_KEY="your-key"

# OpenAI (or any LangChain-compatible LLM)
export OPENAI_API_KEY="your-key"
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Demo

```bash
python run_cross_session.py
```

**What you'll see:**

- **Session 1**: User tells the agent about their business
- **Session 2** (completely new): User returns, agent recalls their
  business details from Session 1 and personalizes its response

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  LangGraph Agent                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ remember  │    │  recall  │    │  answer  │      │
│  │   Tool    │    │   Tool   │    │   Tool   │      │
│  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘   │
│        │               │               │           │
└────────┼───────────────┼───────────────┼───────────┘
         │               │               │
         ▼               ▼               ▼
┌─────────────────────────────────────────────────────┐
│                   Memanto Agent                      │
│  ┌──────────────────────────────────────────────┐   │
│  │     Typed Semantic Memory (13 categories)     │   │
│  │  facts, preferences, decisions, learnings...  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## How It Works

1. **Tool Wrappers** (`memanto_langgraph.py`): LangGraph-compatible
   tool callables that wrap Memanto's `SdkClient`
2. **Agent Graph** (`agent.py`): A StateGraph with three nodes:
   agent (LLM with tools) → tools (Memanto operations) → agent
3. **Cross-Session Demo** (`run_cross_session.py`): Two completely
   separate graph invocations sharing only Memanto memory

## Customizing

### Use a Different LLM

Edit `agent.py` and change `model_name` to any LangChain model:

```python
graph, client, setup = build_customer_support_agent(
    api_key=api_key,
    agent_id="my-agent",
    model_name="gpt-4o",  # or "claude-3-opus", etc.
)
```

### Change the Agent's Behavior

Modify the `SYSTEM_PROMPT` in `agent.py` to customize the agent's
personality, workflow, and memory usage patterns.

### Memory Types

Memanto supports 13 memory types:
`fact`, `preference`, `goal`, `decision`, `artifact`, `learning`,
`event`, `instruction`, `relationship`, `context`, `observation`,
`commitment`, `error`

Use them to categorize memories for better retrieval.

## Requirements

- Python 3.10+
- Memanto API key (free tier: 100 agents, unlimited memories)
- OpenAI API key (or compatible LLM)

## License

MIT — same as the Memanto project.
