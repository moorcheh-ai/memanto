# Memanto + LangGraph: Long-Term Memory for Stateful Agents

This example demonstrates **Memanto as the long-term memory layer for a LangGraph agent**. The agent can store facts across conversation turns and recall them in future sessions — giving your graph a permanent brain.

## How It Works

```
User tells agent: "My birthday is May 1st"
         ↓
  Memanto stores fact [confidence: 0.85]
         ↓
  ─── new session ───
         ↓
User asks: "When is my birthday?"
         ↓
  Memanto recalls stored fact
         ↓
  Agent responds: "Your birthday is May 1st!"
```

## Key Features

- **Cross-Session Recall**: Agent remembers facts from "yesterday" or earlier sessions
- **No External API Required**: Uses Memanto's in-memory store (works offline)
- **Optional LLM Enhancement**: Uses `langchain-openai` if `OPENAI_API_KEY` is set; works without it
- **Memory Trust Scoring**: Each memory has confidence, provenance, and trust level
- **Contradiction Detection**: Built-in conflict handling

## Prerequisites

```bash
pip install memanto langgraph langchain-core langchain-openai
```

```bash
# Optional: for LLM-enhanced responses
export OPENAI_API_KEY=sk-...
```

## Usage

```bash
# Run the cross-session recall demo
python examples/langgraph-memanto/memory_agent.py
```

### Expected Output

The demo runs through two "sessions":
1. **Session 1**: User tells the agent facts (name, birthday, job, hobbies)
2. **Session 2**: New conversation — agent recalls those facts using Memanto

## File Structure

```
examples/langgraph-memanto/
├── memory_agent.py    # Main LangGraph agent with Memanto integration
├── requirements.txt   # Python dependencies
├── README.md          # This file
└── tests/
    └── test_memory_agent.py  # Unit tests
```

## API Overview

### `MemantoStore` (In-Memory)

| Method | Description | Returns |
|--------|-------------|---------|
| `remember(content, title, scope_type, scope_id)` | Store a fact | `memory_id`, `namespace`, `stored_at` |
| `recall(query, scope_type, scope_id)` | Retrieve relevant memories | Ranked list of memories with confidence |
| `get_memory_count(scope_type, scope_id)` | Count memories in scope | Integer |
| `list_memories(scope_type, scope_id)` | List all memories | Titles and metadata |

### `LangGraphMemantoAgent`

| Method | Description |
|--------|-------------|
| `chat(user_input, verbose=True)` | Process a message through the LangGraph pipeline |
| `get_state_summary()` | Get memory count and LLM availability |

## Production Use

For production, replace the in-memory `MemantoStore` with the Memanto/Moorcheh cloud API:

```python
from memanto.app.clients.moorcheh import get_moorcheh_client
client = get_moorcheh_client(api_key="your-key")
```

This enables:
- Semantic vector search across millions of memories
- Multi-agent shared memory
- Persistent storage across server restarts
- Namespace-based memory isolation

## How to Win the Bounty

1. **Star the repo**: https://github.com/moorcheh-ai/memanto
2. **Extend this example**: Add more practical use cases (customer support, personal assistant)
3. **Submit PR**: Fork → add to `examples/langgraph-memanto/` → PR
4. **Amplify**: Post on X/Twitter and Reddit (tag #Memanto @moorcheh-ai)
5. **Score points** by earning upvotes, likes, and reactions
