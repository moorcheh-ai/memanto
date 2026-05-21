# LangGraph + Memanto Cross-Session Memory

This example shows a LangGraph support agent using Memanto as long-term memory outside the graph state. The first run stores a user preference. A later run starts with a fresh LangGraph state, recalls that preference from Memanto, and uses it in the response.

## What It Demonstrates

- Cross-session recall: memory survives across separate graph invocations.
- Memory outside state: LangGraph state is reset between runs; Memanto supplies long-term context.
- Typed memory: preferences are stored as `preference` memories with user and demo tags.
- Safe credentials: API keys are read from environment variables and are never committed.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../..
cp .env.example .env
```

Edit `.env` and set your Moorcheh API key:

```bash
MOORCHEH_API_KEY=your_key_here
```

## Run the Cross-Session Demo

```bash
python run_cross_session_demo.py
```

The demo performs two separate graph sessions:

1. Session 1 stores: "I prefer concise answers and dark mode."
2. Session 2 asks: "What dashboard style should you use for me?"

The second session has no in-memory state from the first one. It can still answer from Memanto recall.

## Single Session Mode

```bash
python run_session.py --user alex --message "I prefer concise answers and dark mode."
python run_session.py --user alex --message "What dashboard style should you use for me?"
```

## Offline Smoke Test

If you only want to verify the LangGraph flow without a Moorcheh API key, use the local JSON fallback:

```bash
python run_cross_session_demo.py --offline
```

The offline mode is included for local development only. The actual integration path uses `MOORCHEH_API_KEY` and Memanto's SDK client.

## Demo Video

Record the terminal output from `python run_cross_session_demo.py` and include the video or GIF link in your PR description.

