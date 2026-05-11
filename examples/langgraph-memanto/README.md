# LangGraph + Memanto: Cross-Session Agent Memory

This example shows a LangGraph support agent using Memanto as long-term memory
outside LangGraph state. A first session stores a user preference. A second,
fresh graph invocation recalls it and uses it to answer.

## What This Demonstrates

- Cross-session recall: a new graph run remembers prior user preferences.
- State separation: LangGraph state only carries the current turn.
- Memanto adapter pattern: the same graph can use local demo storage or the real
  Memanto `SdkClient`.
- No-secret demo path: local JSONL storage proves the control flow without an API
  key.

## Quick Start

```bash
cd examples/langgraph-memanto
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python demo_cross_session.py
```

Expected proof line:

```text
CROSS-SESSION RECALL VERIFIED
```

## Use Real Memanto

```bash
cd examples/langgraph-memanto
cp .env.example .env
export MOORCHEH_API_KEY="your-key"
export MEMANTO_AGENT_ID="langgraph-support-demo"
python demo_cross_session.py
```

When `MOORCHEH_API_KEY` is set, `SdkMemantoStore` creates or reuses the Memanto
agent, activates a session, stores memories through `client.remember`, and
retrieves them through `client.recall`.

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- .env.example
|-- requirements.txt
|-- langgraph_memory_agent.py
|-- demo_cross_session.py
|-- demo/cross_session_recall.md
`-- tests/test_langgraph_memory_agent.py
```

## Workflow

The graph has three nodes:

1. `recall_memanto_memory`: query Memanto-compatible memory before drafting.
2. `draft_answer`: answer using recalled memories only.
3. `write_memanto_memory`: persist durable preferences from the current turn.

That means a second graph invocation can recall preferences even when the
current LangGraph state has no prior messages.

## Demo Artifact

See [`demo/cross_session_recall.md`](./demo/cross_session_recall.md) for the
terminal transcript. The PR video/GIF can be recorded directly from the
Quick Start commands above.
