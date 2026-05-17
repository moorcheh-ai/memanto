# LangGraph + Memanto Recruiting Memory

This example shows a LangGraph recruiting assistant with two separate memory
planes:

- LangGraph `MemorySaver` checkpoints: short-term state for one `thread_id`.
- Memanto: durable semantic memory that survives across different LangGraph
  threads and process runs.

The demo stores candidate context in one thread, then starts a second thread
whose state does not include those facts. The second thread still prepares a
useful interview reminder because it recalls the details from Memanto.

![30-second demo GIF](demo.gif)

## What This Demonstrates

- Cross-session recall across two different LangGraph `thread_id` values.
- A real LangGraph `StateGraph` with recall, response, and durable-write nodes.
- Typed Memanto memories: `fact`, `preference`, and `commitment`.
- A live Memanto SDK backend plus a credential-free local backend for review.
- No LLM dependency. The example is deterministic so reviewers can verify the
  memory boundary without needing a separate model key.

## Architecture

```text
Session 1: intake-2026-05-17
  user notes -> LangGraph -> write_followup_memory -> Memanto

Session 2: briefing-2026-05-18
  empty thread state -> recall_context -> Memanto -> draft_answer
```

The important detail is that Session 2 uses a different LangGraph thread id.
The remembered role, interview style, schedule, and take-home commitment are not
passed in the Session 2 state; they are retrieved from the long-term memory
backend.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run Without API Secrets

Use the local backend when reviewing the PR or running in CI:

```bash
python run_demo.py --backend local --reset-local
python validate_offline.py
```

Expected result:

```text
SESSION 2 - today, thread_id=briefing-2026-05-18
Agent: This is a fresh LangGraph thread, but Memanto recalled yesterday's
durable context:
- Maya Chen role: Yesterday's intake said Maya Chen is interviewing for the
  Staff AI Platform role.
- Maya Chen availability: Maya Chen is available after 14:00 UTC for interviews.
- Maya Chen take-home commitment: The team promised Maya Chen a take-home
  exercise by Friday.
```

## Run With Memanto

Create a Moorcheh API key, then run the same graph against Memanto:

```bash
cp .env.example .env
# Edit .env and set MOORCHEH_API_KEY
python run_demo.py --backend memanto
```

The Memanto backend creates or reuses the `MEMANTO_AGENT_ID`, activates a
session, writes typed memories with `SdkClient.remember()`, and recalls them
with `SdkClient.recall()` in the second LangGraph thread.

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- graph.py              # LangGraph StateGraph
|-- memory_store.py       # Memanto SDK and local review backends
|-- run_demo.py           # Two-session cross-thread demo
|-- validate_offline.py   # Deterministic smoke test
|-- make_demo_gif.py      # Regenerates demo.gif
|-- demo.gif              # 30-second demo asset
`-- demo_transcript.md
```

## Why Memanto Is Outside LangGraph State

LangGraph's checkpointer is excellent for continuing the same thread. This demo
keeps that short-term state, but uses Memanto for facts that should survive
outside any one graph run. That lets a future thread recall candidate context
without copying previous messages into the new state.
