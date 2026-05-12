# LangGraph + Memanto: Persistent Cross-Session Memory

> **Bounty Entry** — [BOUNTY $100] 🐜 The Memanto + LangGraph Integration Challenge
>
> This example shows how to give a [LangGraph](https://langchain-ai.github.io/langgraph/) workflow permanent memory using [Memanto](https://memanto.ai) — so an agent remembers across sessions, across restarts, and across process boundaries.

https://github.com/user-attachments/assets/9855599c-1496-45c8-a8db-0b93a3dedac1

## What This Demonstrates

| Capability | How it's shown |
|-----------|----------------|
| **Cross-session recall** | Run the demo, then run it again — the second run loads memories stored by the first |
| **Typed semantic memory** | Memories are stored with types (`fact`, `preference`, `decision`) and confidence scores |
| **RAG from memory** | The `answer_from_memory` tool synthesizes answers from multiple stored memories |
| **LangGraph integration** | Memanto tools are used inside standard LangGraph `StateGraph` nodes |
| **Zero overhead on existing state** | Memanto supplements LangGraph's built-in `State`, not replaces it — your graph keeps working as-is |

## Architecture

```
                    ┌─────────────────────────┐
                    │     LangGraph Graph      │
                    │  ┌─────────────────────┐ │
  START ──────────▶ │  │ load_context node   │ │ ──▶ recall_memory tool ──▶ Memanto
                    │  └─────────────────────┘ │
                    │  ┌─────────────────────┐ │
                    │  │ store_memories node │ │ ──▶ remember_memory tool ──▶ Memanto
                    │  └─────────────────────┘ │
                    │  ┌─────────────────────┐ │
                    │  │ answer_question node│ │ ──▶ answer_from_memory tool ──▶ Memanto
                    │  └─────────────────────┘ │
                    │  ┌─────────────────────┐ │
                    │  │ summarize node      │ │
                    │  └─────────────────────┘ │
                    └──────────┬──────────────┘
                               │
                    ╔══════════╧══════════╗
                    ║     Memanto SDK     ║
                    ║  remember / recall  ║
                    ║  / answer           ║
                    ╚═════════════════════╝
                               │
                    ┌──────────┴──────────┐
                    │  Moorcheh API       │
                    │  (serverless,       │
                    │   zero idle cost)   │
                    └─────────────────────┘
```

### Why tools, not a storage backend override?

LangGraph stores conversation state in its own `State` — this is good for single-session, in-progress state. But that state is gone when the process exits.

Memanto fills the gap: **permanent, queryable, cross-session memory**. We expose it as *tools* that the LangGraph graph calls at specific nodes:

- At **startup**: `recall_memory` retrieves what the agent knows about the user
- During **processing**: `remember_memory` stores new facts and preferences
- On **demand**: `answer_from_memory` synthesizes answers from stored memories

This keeps Memanto's memory system **independent** of the LangGraph state lifecycle. Your graph keeps its existing state handling; Memanto adds persistence on top.

## Quick Start

### Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)

### Setup

```bash
# 1. Navigate to the example
cd examples/langgraph-memanto

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

### Run

```bash
export MOORCHEH_API_KEY="sk-..."  # or set in .env
python run_cross_session.py
```

**First run:** Creates a Memanto agent, stores preferences and decisions, then exits.

**Second run** (proves cross-session recall!):
```bash
python run_cross_session.py
```
The startup node automatically loads the memories stored by the first run. You'll see the agent say:
```
Context loaded: Existing memories for this user:
  [preference, conf=0.8] Dark mode preference: The user prefers dark mode...
  [fact, conf=0.8] Timezone: The user's timezone is Asia/Shanghai...
```

## File Structure

```
examples/langgraph-memanto/
├── README.md               # This file
├── requirements.txt        # Python dependencies
├── .env.example            # API key template
├── memanto_tools.py        # Memanto → LangChain Tool wrappers
│                            #   - MemantoSetup: bootstrap helper
│                            #   - create_memanto_tools(): returns remember/recall/answer tools
└── run_cross_session.py    # Main demo: LangGraph StateGraph with Memanto memory
```

## Memanto Tools Reference

| Tool | SDK Method | Description |
|------|-----------|-------------|
| `remember_memory` | `SdkClient.remember()` | Store a memory with type, confidence, tags |
| `recall_memory` | `SdkClient.recall()` | Semantic search of stored memories |
| `answer_from_memory` | `SdkClient.answer()` | RAG-based answer from memory context |

### Using the Tools in Your Own Graph

```python
from memanto_tools import MemantoSetup, create_memanto_tools

# 1. Setup
setup = MemantoSetup(api_key="sk-...")
client = setup.setup(agent_id="my-custom-agent")
tools = create_memanto_tools(client, agent_id="my-custom-agent")

# 2. Use inside any LangGraph node
def my_node(state):
    # Store something
    tools["remember"].invoke({
        "input": '{"content": "Learned X", "memory_type": "fact"}'
    })
    # Recall later
    memories = tools["recall"].invoke(
        {"query": "What did I learn about X?"}
    )
    return {"messages": [("assistant", memories)]}

# 3. Cleanup
setup.teardown()
```

## How to Win the Social Traction Bonus

The bounty uses a "Social Traction Formula" to rank entries. Here's how to max your score:

| Action | Platform | Points |
|--------|----------|--------|
| Post your demo + link to PR | X/Twitter, tag @moorcheh_ai + #Memanto | 1pt per like, 3pt per RT/bookmark |
| Share in a relevant Reddit community | r/LangGraph, r/LocalLLaMA, r/MachineLearning | 5pt base + 2pt per upvote |
| Add a 🚀 reaction on the PR | GitHub | 2pt each |

### Suggested Posts

**X/Twitter:**
> 🧠 Gave my LangGraph agent permanent memory using @moorcheh_ai's Memanto.
>
> It remembers across sessions — preferences, facts, decisions — even after the process exits.
>
> 🔗 [link to your PR]
> #Memanto #LangGraph #AIAgents

**Reddit (r/LangGraph):**
> Title: I gave my LangGraph agent permanent cross-session memory with Memanto
>
> Body: LangGraph's built-in State is great for single sessions, but what about long-term memory? Here's a clean integration where Memanto handles persistence while LangGraph handles orchestration. Full code in the PR linked below.

## Comparison: Memanto vs. LangGraph Built-in Memory

| Feature | LangGraph State | Memanto (via this integration) |
|---------|----------------|--------------------------------|
| Scope | Single session | Cross-session, cross-process |
| Persistence | Lost on exit | Permanent (serverless) |
| Search | Key-based access only | Semantic / natural-language query |
| Memory types | Untyped | 13 semantic types (fact, preference, decision, goal, …) |
| Confidence | N/A | 0.0–1.0 scoring |
| Conflict detection | N/A | Automatic contradiction detection |
| RAG | N/A | Built-in `answer()` with source citations |
| Cost at idle | N/A | Zero (serverless) |

## Learn More

- [Memanto Documentation](https://docs.memanto.ai)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
