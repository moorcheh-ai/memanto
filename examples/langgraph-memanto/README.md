# LangGraph + Memanto: Cross-Session Memory for Stateful Agents

**Bounty #397 Submission** — Demonstrates Memanto as the long-term memory layer for LangGraph agents.

## What This Demonstrates

- **Cross-session recall**: Agent remembers user preferences from previous conversations
- **LangGraph state + Memanto memory**: LangGraph handles conversation flow, Memanto handles long-term facts
- **Real-world use case**: Customer support agent that learns user preferences over time
- **Clean architecture**: Modular, tested, production-ready

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Workflow                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │  Greet   │───▶│  Query   │───▶│ Respond  │              │
│  │  User    │    │ Memanto  │    │ & Store  │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│       │               │                │                     │
│       └───────────────┼────────────────┘                     │
│                       ▼                                      │
│              ┌─────────────────┐                            │
│              │  Memanto Memory │                            │
│              │  (Persistent)   │                            │
│              └─────────────────┘                            │
└─────────────────────────────────────────────────────────────┘

Session 1: User says "I prefer dark mode"
          → Stored in Memanto as preference

Session 2 (next day): User asks "What's my theme?"
                     → LangGraph queries Memanto
                     → Returns "dark mode" from yesterday
```

## Prerequisites

- Python 3.10+
- [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier available)
- OpenAI API key (or any LLM provider)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY

# Run Session 1: Store user preferences
python session1_store.py

# Run Session 2: Recall from previous session (proves cross-session memory!)
python session2_recall.py
```

## Demo Video

[30-second demo showing cross-session recall]

## Technical Details

### LangGraph State
- Handles current conversation flow
- Manages turn-by-turn context
- Resets between sessions

### Memanto Memory
- Stores long-term facts (preferences, history, decisions)
- Persists across sessions
- Queryable by semantic similarity

### Integration Pattern
```python
# Store in Memanto during conversation
memanto.remember(
    content="User prefers dark mode",
    memory_type="preference",
    confidence=0.95
)

# Recall in future sessions
results = memanto.recall("What are user's UI preferences?")
```

## Files

- `agent.py` — LangGraph workflow definition
- `session1_store.py` — First conversation (stores preferences)
- `session2_recall.py` — Second conversation (recalls from Memanto)
- `requirements.txt` — Dependencies
- `.env.example` — API key template
- `tests/` — Unit tests

## Social Media

[Twitter/X post link]
[Reddit post link]

---

Built with ❤️ for the Memanto bounty challenge
