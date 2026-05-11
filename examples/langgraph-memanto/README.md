# LangGraph + Memanto: Cross-Session Support Memory

This example shows a LangGraph support agent using Memanto as the long-term
memory layer outside the graph state. The first support session stores an
explicit user preference. The second session starts with fresh LangGraph state
and still recalls that preference through Memanto.

![LangGraph + Memanto demo](./demo.gif)

## What This Demonstrates

- Cross-session recall: session 2 remembers a preference from session 1.
- External memory boundary: the preference is not copied into LangGraph state.
- Typed memories: support preferences are stored as Memanto `preference`
  records with confidence, provenance, and tags.
- Reviewable offline mode: `--mock-memory` mirrors the Memanto contract so the
  graph can be inspected without a Moorcheh API key.

## Architecture

```text
Session 1 state
  -> LangGraph recall_context node
  -> draft_reply node
  -> persist_new_preferences node
  -> Memanto remembers "Alex prefers concise answers..."

Session 2 state (fresh, no prior preference in state)
  -> LangGraph recall_context node
  -> Memanto recalls Alex's preference
  -> draft_reply uses recalled memory
```

The graph only passes `user_id`, `session_id`, `message`,
`recalled_memories`, and `reply`. Long-term preferences live in Memanto, not in
the state object.

## Prerequisites

- Python 3.10+
- A Moorcheh API key from https://console.moorcheh.ai/api-keys

Install from the repository root:

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -e ../..
pip install -r requirements.txt
```

## Run With Memanto

```bash
cp .env.example .env
# Edit .env and set MOORCHEH_API_KEY
python support_agent.py
```

Expected shape:

```text
Session 1: capture an explicit preference
Stored memory id: ...

--- LangGraph state reset between sessions ---
Session 2 only includes user_id and the new question.
Session 2026-05-11 reply for alex:
- Remembered context: alex prefers concise support answers and wants technical detail links when useful.
```

## Offline Review Mode

If you do not have a Moorcheh API key, run the same LangGraph workflow with the
file-backed mock gateway:

```bash
python support_agent.py --mock-memory --reset
```

The mock gateway writes to `/tmp/memanto-langgraph-support-memory.json` so the
demo still proves that memory survives the graph state reset. Use real Memanto
for production behavior.

## File Structure

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── requirements.txt
├── support_agent.py
└── demo.gif
```

## Why This Pattern

LangGraph is excellent at per-run orchestration state. Memanto is better suited
for durable facts, preferences, and decisions that need to survive disjointed
sessions. Keeping them separate prevents hidden state coupling: LangGraph owns
the current workflow, Memanto owns long-term recall.
