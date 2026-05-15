# LangGraph + Memanto Example

This example shows Memanto acting as a long-term memory layer outside a
LangGraph state machine. The graph stores structured memories during one
support conversation, then a fresh graph thread recalls those memories to
personalize a follow-up response.

The important separation is intentional:

- LangGraph state carries short-lived workflow data such as the current message.
- Memanto stores durable memories that survive graph runs and thread IDs.
- The second run starts with a new LangGraph state, but still retrieves the
  customer's remembered preferences, commitments, and prior events.

## What It Demonstrates

- Durable memory across LangGraph invocations
- Typed memory writes with `preference`, `event`, `decision`, and `commitment`
- Recall before response generation so the graph can ground its output
- A deterministic offline response path for demos without an LLM key
- Optional OpenAI-backed generation if `OPENAI_API_KEY` is configured

## Setup

Run from this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../..
cp .env.example .env
```

Edit `.env` and set `MOORCHEH_API_KEY`.

## Run The Demo

```bash
python run_demo.py
```

Expected flow:

1. The first graph run stores a customer's plan, preference, incident, and
   escalation commitment in Memanto.
2. The script starts a separate graph run with a different `thread_id`.
3. The second run recalls the durable memories and produces a support reply
   that uses them.

You can run the script repeatedly with the same `AGENT_ID` to demonstrate that
Memanto persists beyond one process run.

## Optional LLM Mode

By default, the demo uses a deterministic local response composer. To use a real
chat model for the final support response:

```bash
export OPENAI_API_KEY=...
export LANGGRAPH_MEMANTO_MODEL=gpt-4o-mini
python run_demo.py
```

The memory writes and recall path remain the same; only the final response
generation changes.
