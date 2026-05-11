# LangGraph + Memanto: Cross-Session Agent Memory

This example shows a LangGraph support-agent workflow using Memanto as the
long-term memory layer. The graph state only contains the current user message,
current recall results, and current response. Anything that must survive future
sessions is stored in Memanto and recalled by a later graph invocation.

## What It Demonstrates

- Cross-session recall: run one script to store user preferences, then run a
  second script in a fresh process to recall them.
- Memanto outside graph state: persistent facts and preferences are written to
  Memanto, not carried in LangGraph checkpoints or process globals.
- Typed semantic memory: extracted user details are stored as `fact` and
  `preference` memories with confidence scores and tags.
- Deterministic graph nodes: the demo uses simple rule-based extraction so it
  runs without a separate LLM key.

## Demo Recording

The bundled 30-second GIF shows the two-session flow at a glance. You can
reproduce the same flow locally by running `python run_full_demo.py` after
setup:

[30-second LangGraph + Memanto demo](./assets/langgraph-memanto-demo.gif)

## Architecture

```text
User message
  -> recall_context    reads relevant long-term memories from Memanto
  -> remember_context  stores explicit new facts/preferences in Memanto
  -> draft_response    answers using the recalled memory context
```

The second run starts with an empty LangGraph state and a new Memanto session,
but it uses the same `MEMANTO_AGENT_ID`. That shared agent namespace is the
persistence boundary.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```bash
MOORCHEH_API_KEY=your-moorcheh-api-key
MEMANTO_AGENT_ID=langgraph-memanto-support
```

## Run The Cross-Session Demo

Run session one. It stores explicit user facts and preferences in Memanto:

```bash
python run_session_one.py
```

Then run session two. This starts a new process and recalls the preferences
stored by session one:

```bash
python run_session_two.py
```

You can also run the two-session flow in one command. The helper closes and
re-opens the Memanto session between graph invocations:

```bash
python run_full_demo.py
```

## Expected Output Shape

Session one should report no prior memories, then list new memory IDs. Session
two should show recalled memories similar to:

```text
Persistent memory recalled from Memanto:
1. [fact] User name: User's name is Maya.
2. [preference] User preference: User prefers vegetarian meal kits.
3. [preference] User aversion: User dislikes cilantro.

Support answer:
I will use the recalled preferences above instead of asking you to repeat them.
```

## Offline Smoke Test

For local graph wiring checks without a Moorcheh API key, set:

```bash
MEMANTO_OFFLINE_DEMO=1
python run_full_demo.py
```

This uses `.langgraph-memanto-demo.json` as a tiny local store. Leave
`MEMANTO_OFFLINE_DEMO` unset when demonstrating the actual Memanto integration.
