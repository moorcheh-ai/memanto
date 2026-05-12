# LangGraph + Memanto: Research Assistant with Cross-Session Memory

A practical example of using **Memanto** as the persistent long-term memory layer for a **LangGraph** agent. This research assistant remembers user interests, past topics, and findings across completely disjoint sessions — demonstrating true cross-session recall.

## What This Demonstrates

- **Cross-Session Recall**: Session 2 remembers what was researched in Session 1, even with a new LangGraph thread
- **Typed Semantic Memory**: Uses Memanto's `fact`, `preference`, and `finding` memory types
- **Temporal Awareness**: Recalls recent activity across time windows (hours, days, weeks)
- **Deduplication**: Merges and deduplicates related memories from different sources
- **Three-Primitive API**: Uses Memanto's `remember`, `recall`, and `answer` operations

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph Agent                       │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  RECALL  │───▶│ RESPOND  │───▶│ REMEMBER │──▶ END   │
│  │ (memory) │    │  (LLM)   │    │ (persist)│          │
│  └────┬─────┘    └──────────┘    └────┬─────┘          │
│       │                               │                 │
└───────┼───────────────────────────────┼─────────────────┘
        │                               │
        ▼                               ▼
   ┌─────────────────────────────────────────┐
   │              Memanto                      │
   │  ┌──────┐  ┌──────┐  ┌──────┐           │
   │  │remember│  │recall│  │answer│           │
   │  └──────┘  └──────┘  └──────┘           │
   │       Persistent Cross-Session Memory     │
   └─────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) (for the LangGraph LLM)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

## Usage

```bash
python agent.py
```

You'll see two sessions:

1. **Session 1**: The user researches "quantum computing applications in drug discovery"
2. **Session 2** (new thread, days later): The user asks "what did I research before about quantum computing?" — the agent recalls Session 1's context from Memanto

## Key Code Patterns

### Storing a memory

```python
from memanto import MemantoClient

client = MemantoClient()
client.remember(
    content="User researched: quantum computing in drug discovery",
    memory_type="fact",
    title="Research topic: quantum computing",
    confidence=0.95,
    scope_type="user",
    scope_id="user-123",
)
```

### Cross-session recall

```python
# Days later, new LangGraph thread, same user
memories = client.recall(
    query="quantum computing research",
    limit=5,
    scope_type="user",
    scope_id="user-123",  # Same user — memories persist!
)

for m in memories:
    print(f"[{m['type']}] {m['title']}: {m['content']}")
```

## Demo Video

<!-- Add a 30-second GIF or video link here showing:
     1. Session 1: Agent researches a topic and stores memories
     2. Session 2: Agent recalls the past research context
     -->

## Social Traction

If you find this example useful:
- Star the [Memanto repo](https://github.com/moorcheh-ai/memanto) ⭐
- Share on X/Twitter: Tag #Memanto and @moorcheh_ai
- React to the PR on GitHub

---

Built for the [Memanto + LangGraph Integration Challenge](https://github.com/moorcheh-ai/memanto/issues/397) ($100 bounty).
