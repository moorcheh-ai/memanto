# LangGraph + Memanto Example

This example shows how to use **Memanto** as a long-term memory layer for a
LangGraph customer support agent. The graph keeps only the current request in
LangGraph state; preferences, account context, and prior decisions live in
Memanto so they can be recalled in a later run.

## What This Demonstrates

- **Cross-session recall**: `seed_memory.py` stores memories, and
  `run_support_agent.py` recalls them in a separate process.
- **Memory outside graph state**: the LangGraph state contains the current
  support message and response, not the user's full history.
- **Typed semantic memory**: preferences, facts, and commitments are stored as
  distinct memory types.
- **Practical support workflow**: the agent retrieves relevant context before
  drafting a response.

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys)

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

If you are running from a local checkout of this repository, install Memanto in
editable mode from the repository root:

```bash
pip install -e ../..
```

If you are copying this example into another project, install Memanto from PyPI:

```bash
pip install memanto
```

## Run The Cross-Session Demo

Run the two scripts as separate commands. This proves that the second graph run
can recall facts that are not present in its current LangGraph state.

```bash
# Day 1: store support context in Memanto
python seed_memory.py

# Day 2: start a fresh LangGraph run and recall the prior context
python run_support_agent.py
```

Expected output from `run_support_agent.py`:

```text
Recalled long-term memories:
- User prefers concise answers with bullet points.
- User is on the Pro plan and works from Europe/London.
- Follow up after the billing migration completes.

Draft response:
...
```

## File Structure

```text
examples/langgraph-memanto/
├── README.md
├── requirements.txt
├── .env.example
├── memory_client.py
├── seed_memory.py
└── run_support_agent.py
```

## Recording Checklist

For a short demo video or GIF:

1. Run `python seed_memory.py`.
2. Clear the terminal.
3. Run `python run_support_agent.py`.
4. Point out that the second script has no hard-coded user profile in graph
   state, but still recalls prior preferences from Memanto.
