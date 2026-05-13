# LangGraph + Memanto Support Memory Demo

This example wires Memanto into a LangGraph customer-support workflow. The graph
recalls long-term customer context before drafting a response, then stores any
new preference it learns for the next session.

## What It Demonstrates

- A LangGraph `StateGraph` with memory recall, response drafting, and memory
  persistence nodes.
- Memanto as the long-term memory layer for customer preferences and support
  context.
- Cross-session recall: run one script to store context, then a second script to
  retrieve it in a fresh session.
- A deterministic demo path that does not require a separate LLM API key.

## Architecture

```text
Support ticket
    |
    v
LangGraph recall_memory node
    |
    v
Memanto recall(customer context)
    |
    v
LangGraph draft_reply node
    |
    v
LangGraph persist_preference node
    |
    v
Memanto remember(new preference)
```

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
```

Add your `MOORCHEH_API_KEY` to `.env`, or export it in your shell.

## Run The Cross-Session Demo

```bash
python run_seed_session.py
python run_recall_session.py
```

The first command stores this preference for `cust-acme-42`:

```text
Customer cust-acme-42 prefers concise, action-oriented support replies with
bullet points.
```

The second command starts a fresh workflow session and recalls that preference
before drafting a reply for a new ticket.

## Demo Recording

Use [demo-script.md](demo-script.md) to record a 30-second GIF or video. The
recording should show the seed command storing a preference and the recall
command using it in a separate session.

## Files

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── requirements.txt
├── client_factory.py
├── memory_adapter.py
├── workflow.py
├── run_seed_session.py
├── run_recall_session.py
└── demo-script.md
```
