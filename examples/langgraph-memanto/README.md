# LangGraph + Memanto: Give Your Graph a Permanent Brain

This example shows how **Memanto** acts as the long-term memory layer for a
LangGraph agent, enabling **cross-session recall** — the agent remembers what
a user told it yesterday even though LangGraph's own state is wiped between
processes.

> **Demo video / GIF:** *(record a 30-second terminal session showing
> `run_session1.py` storing memories and `run_session2.py` recalling them,
> then replace this line with the link)*

---

## What This Demonstrates

| Capability | Mechanism |
|---|---|
| **Cross-session recall** | Memanto memories persist across Python processes / LangGraph threads |
| **Long-term user context** | Name, device, plan, past issues recalled without any LangGraph state |
| **Typed semantic memory** | 13 Memanto memory types (fact, preference, event, commitment…) |
| **Zero-boilerplate** | A single `MemantoMemory` wrapper handles agent lifecycle |

---

## Architecture

```
  User message
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                    LangGraph State Machine                      │
  │                                                                 │
  │   START                                                         │
  │     │                                                           │
  │     ▼                                                           │
  │  recall_context   ── queries Memanto before the LLM fires       │
  │     │                                                           │
  │     ▼                                                           │
  │  generate_response ─ LLM + recalled context + chat history      │
  │     │                                                           │
  │     ▼                                                           │
  │  persist_memories ─ LLM extracts facts → stored in Memanto      │
  │     │                                                           │
  │     ▼                                                           │
  │    END                                                          │
  └─────────────────────────────────────────────────────────────────┘
        │  reads / writes              │  reads / writes
        ▼                             ▼
  ┌──────────────────┐       ┌──────────────────────────┐
  │  LangGraph       │       │  Memanto (Moorcheh API)  │
  │  MemorySaver     │       │                          │
  │                  │       │  fact, preference,        │
  │  within-session  │       │  event, commitment…       │
  │  history only    │       │                          │
  │  (lost on exit)  │       │  persists FOREVER        │
  └──────────────────┘       └──────────────────────────┘
```

---

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) **or** an
  [OpenRouter key](https://openrouter.ai/keys) (free tier available)

---

## Setup

```bash
cd examples/langgraph-memanto
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — add MOORCHEH_API_KEY and OPENAI_API_KEY
```

---

## Step-by-Step Demo (proves cross-session persistence)

### Step 1 — Session 1: Alice introduces herself

```bash
python run_session1.py
```

The agent greets Alice, responds to her messages, and stores structured memories
in Memanto after each turn:

```
[Turn 1]
Alice : Hi there! My name is Alice Chen. I'm having trouble with my account.
Agent : Hi Alice! I'm Alex from customer support...

[Turn 3]
Alice : I was charged twice for my Pro subscription last month...
Agent : I'm sorry to hear that, Alice. I've noted the duplicate charge...
```

### Step 2 — Session 2: Alice returns (new Python process, zero LangGraph state)

```bash
python run_session2.py
```

A brand-new Python process — LangGraph's `MemorySaver` is completely empty.
Every piece of context the agent uses comes **exclusively from Memanto**:

```
SESSION 2 — Alice returns in a NEW Python process

  LangGraph MemorySaver : EMPTY  (no state from Session 1)
  Memanto               : FULL   (all memories from Session 1 persist)

[Turn 1]
Alice : Hey, it's me again. Did my refund request go through?
Agent : Hi Alice! I remember you reported a duplicate charge on May 3rd and May 17th...
        I've followed up on your refund request...
```

The agent recalls Alice's name, MacBook Pro M3, Pro plan, and billing issue
**without any LangGraph state from Session 1**.  That is Memanto's permanent brain.

---

## File Structure

```text
examples/langgraph-memanto/
├── README.md            ← this file
├── requirements.txt     ← Python dependencies
├── .env.example         ← API key template
├── memanto_memory.py    ← MemantoMemory wrapper (lifecycle + recall/remember)
├── agent.py             ← LangGraph graph (recall_context → generate_response → persist_memories)
├── run_session1.py      ← Session 1: Alice's first conversation (stores memories)
└── run_session2.py      ← Session 2: Alice returns (cross-session recall demo)
```

---

## How the Nodes Work

### `recall_context`

Fires **before** the LLM on every turn.  Queries Memanto with the user's latest
message using semantic search, formats the results into a context block, and
injects it into the system prompt.

### `generate_response`

Standard LLM call (`ChatOpenAI`).  The system prompt is dynamically built from
the base persona **plus** the recalled Memanto memories.  If no memories are
found (new user), the agent introduces itself and gathers context.

### `persist_memories`

A second (cheap) LLM call that extracts 0–3 atomic, typed memories from the
latest conversation turn and stores each one in Memanto via `MemantoMemory.remember()`.
This is best-effort — a storage failure never crashes the graph.

---

## Production Notes

- **User isolation**: memories are scoped to the `agent_id` namespace.  For
  multi-user production systems, create one Memanto agent per user, or include
  the `user_id` as a tag and filter by it in `recall()`.
- **Indexing latency**: Memanto indexes memories asynchronously.  Within-session
  recall of memories stored in the same run may have a brief delay.
  Cross-session recall (the focus of this demo) is always reliable.
- **LLM provider**: swap `langchain-openai` for `langchain-anthropic` and set
  `model="claude-sonnet-4-6"` if you prefer Claude.

---

## Bonus: Access the Same Memories from Cursor

After running the demo, you can query Alice's memories directly from Cursor:

```bash
memanto connect cursor --global
```

Then in any Cursor project:

> "Use memanto recall to find what Alice said about her subscription plan"
