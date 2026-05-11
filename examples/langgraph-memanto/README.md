# LangGraph + Memanto Example

A minimal, production-shaped [LangGraph](https://github.com/langchain-ai/langgraph)
support-concierge agent that uses **Memanto** as its long-term memory layer.

LangGraph already gives you stateful, multi-step agent workflows. The piece it
intentionally does *not* solve is **durable memory across sessions** — the
graph's `MessagesState` is per-run. This example demonstrates a clean pattern
for snapping Memanto in as the cross-session memory layer so the agent
*genuinely* remembers the user between disjointed runs of the program.

> Closes the technical criterion from [issue #397](https://github.com/moorcheh-ai/memanto/issues/397):
> *"Must demonstrate Cross-Session Recall (The agent remembers something from
> 'yesterday' that isn't in the current thread's state)."*

## Demo Video

> **TODO (PR author):** Replace this line with a 30-second screencast GIF or
> Loom / YouTube link showing `run_session_1.py` followed by
> `run_session_2.py` from a fresh process.

## What This Demonstrates

- **Cross-session recall** — `run_session_1.py` stores facts; `run_session_2.py`
  is a separate process with an empty LangGraph state and the agent still
  answers correctly by recalling from Memanto.
- **Drop-in memory layer** — `memanto_memory.py` exposes a tiny
  `MemantoMemory` facade that any LangGraph node can call.
- **Memory extraction, not just storage** — the graph has a dedicated
  `extract` node that uses the LLM in JSON mode to pull *durable* facts out
  of each user turn before writing them to Memanto. The assistant's own
  output is never stored as ground truth.
- **Typed memory** — preferences, facts, decisions, and goals are stored
  with the right Memanto memory type so retrieval is clean.

## Graph Shape

```
       +--------+     +---------+     +---------+
USER ->| recall |  -> | respond |  -> | extract | -> END
       +--------+     +---------+     +---------+
            |              |                |
            v              v                v
       Memanto.recall   LLM.invoke     Memanto.remember
```

- `recall` — semantic-search Memanto with the latest user message; stash
  results in the graph state.
- `respond` — call the LLM with system prompt + recalled memories + the
  current turn.
- `extract` — JSON-mode LLM call that returns atomic memories to write to
  Memanto. Only the user's input is mined; the assistant's reply is treated
  as ephemeral.

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) — free tier is plenty.
- An [OpenRouter API key](https://openrouter.ai/keys) — `openai/gpt-4o-mini`
  is the default; any tool-capable chat model works.

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then edit and fill in the two API keys
```

## Run the cross-session demo

The two scripts are designed to be run in **two separate processes** with
nothing shared but Memanto:

```bash
# Step 1: Capture context (preferences, region, migration plans, ...)
python run_session_1.py

# Step 2: Brand-new process, empty LangGraph state.
# The agent answers correctly only because Memanto remembers.
python run_session_2.py
```

`run_session_2.py` exits non-zero if the assistant's replies fail to
reference at least two of the facts captured in session 1 — so it doubles
as a smoke test.

### Interactive mode

```bash
python run_chat.py
```

Drop into a REPL with the same memory namespace. Useful for recording the
30-second screencast the bounty asks for.

## Files

| File | What it does |
|------|--------------|
| `memanto_memory.py` | `SdkClient` lifecycle + `remember` / `recall` / `answer` facade + a context manager that handles agent create/activate/deactivate. |
| `graph.py` | `recall -> respond -> extract` LangGraph workflow plus tiny helpers (`initial_state`, `assistant_reply`). |
| `run_session_1.py` | Run 1 — user shares context. |
| `run_session_2.py` | Run 2 — fresh process; agent recalls. |
| `run_chat.py` | Interactive REPL for demos. |
| `requirements.txt` | `memanto`, `langgraph`, `langchain-openai`, `python-dotenv`. |
| `.env.example` | `MOORCHEH_API_KEY` + `OPENROUTER_API_KEY` template. |

## Notes on memory hygiene

- We only feed the **latest user turn** into the extractor; the assistant's
  reply is never written to memory. This is the difference between *what
  the user told us* (durable) and *what the bot said back* (ephemeral).
- The extractor returns strict JSON and is validated against Memanto's
  13 allowed memory types before writing. Malformed candidates are dropped.
- `recall` uses semantic similarity; we cap to 6 memories per turn to keep
  the prompt tight. Tune with `memory.recall(..., limit=N)`.
- The Memanto agent id is shared across all three scripts
  (`langgraph-support-concierge`); changing it gives you a clean namespace
  for a different demo.
