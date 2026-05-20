# LangGraph + Memanto Social Showcase

Use this file when sharing the demo for the Memanto + LangGraph bounty. The technical proof is local and repeatable, while the post copy is ready for X, LinkedIn, or Reddit.

## Short Post

```text
I built a LangGraph + Memanto support-agent example that gives a graph durable memory across sessions without storing old messages in LangGraph state.

Session 1 stores Riley's account facts.
Session 2 starts fresh and still recalls the account, invoice, and migration details from Memanto.

PR: https://github.com/moorcheh-ai/memanto/pull/518
#Memanto @moorcheh-ai
```

## Longer Post

```text
I built a LangGraph + Memanto example for cross-session agent memory.

The key boundary:
- LangGraph state is fresh in the second run.
- No previous messages are injected into the new graph state.
- Memanto stores and retrieves the durable memories.
- The validator checks that every recalled memory came from yesterday's session, not today's graph state.

The example includes:
- a LangGraph StateGraph support-agent workflow
- local JSON review mode with no credentials
- optional live Memanto SDK mode
- tests for the memory boundary
- a 30-second demo GIF in the README

PR: https://github.com/moorcheh-ai/memanto/pull/518
#Memanto @moorcheh-ai
```

## Demo Proof

Run from `examples/langgraph-memanto`:

```bash
python validate_offline.py
PYTHONPATH=. python -m pytest tests -q
```

Expected output:

```text
offline validation passed
recalled_memories=3
state_boundary=passed
```

## What The Demo Shows

1. `support-yesterday` stores Riley's dashboard, invoice, and migration facts in Memanto.
2. `support-today` starts as a new LangGraph run with no prior messages.
3. The response still recalls Riley's Northstar dashboard, Friday purchase order deadline, and May 28 migration date.
4. `validate_offline.py` fails if the current graph state supplies the recalled memories.
