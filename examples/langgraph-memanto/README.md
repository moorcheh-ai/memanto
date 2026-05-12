# LangGraph + Memanto: Customer Support Agent with Persistent Memory

A LangGraph agent that gives your state graph a **permanent brain** via Memanto.
The agent remembers customer preferences and past issues across completely separate
Python sessions — no shared process, no shared in-memory state.

## What This Demonstrates

- **Cross-Session Recall** — Run Session 1 today, Session 2 tomorrow.
  The agent retrieves customer preferences from Memanto without any in-memory handoff.
- **Typed semantic memory** — Facts, preferences, and observations stored with
  Memanto's 13 memory types and confidence scoring.
- **Clean LangGraph integration** — Three dedicated nodes: `recall → respond → remember`.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  LangGraph StateGraph               │
│                                                     │
│  [recall]  →  [respond]  →  [remember]  →  END     │
│     │              │              │                 │
│     ▼              ▼              ▼                 │
│  Memanto        ChatOpenAI     Memanto              │
│  (search)       (generate)    (store)               │
└─────────────────────────────────────────────────────┘

Cross-session persistence: Memanto ↔ Moorcheh vector store
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/moorcheh-ai/memanto.git
cd memanto/examples/langgraph-memanto

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and add MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Step-by-Step Demo (Proves Cross-Session Recall)

```bash
# Session 1: agent stores customer facts in Memanto
python run_session_1.py

# Session 2: brand-new session — agent recalls from Memanto
python run_session_2.py
```

**Expected output of Session 2:**

```
>> Memories retrieved from Memanto (cross-session):
[score=0.94] [FACT] Customer prefers dark mode
              The customer explicitly stated they prefer dark mode in the UI.
[score=0.87] [FACT] Customer is based in Tokyo
              ...

User: Hey, do you remember what city I'm in? Also, what's my UI preference?
Agent: Of course! You're based in Tokyo, and you prefer dark mode. ...
```

## File Structure

```
langgraph-memanto/
├── agent.py           # Core graph definition (recall → respond → remember)
├── run_session_1.py   # Session 1: store memories
├── run_session_2.py   # Session 2: recall across sessions (proves persistence)
├── requirements.txt
└── .env.example
```

## How It Works

### The Three Nodes

| Node | Action | Memanto API |
|------|--------|-------------|
| `recall` | Fetch customer memories relevant to the current query | `client.search()` |
| `respond` | Generate reply using memories as context; extract key facts | OpenAI |
| `remember` | Persist newly extracted facts to Memanto | `client.store()` |

### Namespace Design

Each customer gets an isolated namespace: `memanto_agent_{customer_id}`.
Switching `customer_id` in state gives each customer their own memory space.

## Running Without a GIF

Record a terminal session with [asciinema](https://asciinema.org/):

```bash
asciinema rec demo.cast
python run_session_1.py
python run_session_2.py
exit
asciinema upload demo.cast
```

## License

[Apache 2.0](../../LICENSE)
