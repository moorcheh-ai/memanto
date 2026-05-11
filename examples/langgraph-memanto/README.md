# LangGraph + Memanto: Cross-Session Agent Memory

This example shows a LangGraph support agent using Memanto as durable memory
outside the graph state. It proves that a fresh graph invocation can recall
facts from an earlier session without carrying them in the current thread.

![LangGraph + Memanto demo](./demo.gif)

## What This Demonstrates

- A real `StateGraph` workflow with recall, response, and memory-write nodes.
- Cross-session recall: session two remembers details written by session one.
- A Memanto-backed adapter for live Moorcheh/Memanto storage.
- A local JSON adapter so reviewers can run the demo without API keys.
- Focused offline validation for CI or bounty review.

## Architecture

```text
Session 1
  user message -> recall node -> respond node -> write memory node
                                             |
                                             v
                                    Memanto durable memory
                                             ^
                                             |
Session 2
  fresh graph state -> recall node -----------+
                  -> respond node uses recalled facts
                  -> write memory node
```

The important boundary is that the LangGraph state only contains the current
messages and the memories returned for this invocation. Long-term facts live in
the memory backend.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## Offline Demo

The offline backend uses `.memanto_local_store.json` and needs no secrets.

```bash
python run_demo.py --backend local --reset-local
```

Expected signal:

```text
Session 2 recalled:
- Customer Riley runs Acme Robotics order AR-8841.
- Riley prefers concise answers with no marketing language.
- Refunds above $500 require manager approval.
```

## Live Memanto Demo

Set a Moorcheh API key and run the same graph against Memanto:

```bash
set MOORCHEH_API_KEY=your-key
python run_demo.py --backend memanto --agent-id langgraph-memanto-demo
```

The live adapter creates the agent if needed, activates a session, writes
memories with typed metadata, and recalls them through Memanto.

## Validate

```bash
python validate_offline.py
```

The validation resets the local store, runs the two-session demo, and fails if
the second session does not recall the order number, preference, and approval
rule from durable memory.

## File Structure

```text
examples/langgraph-memanto/
  README.md
  demo.gif
  langgraph_memanto.py
  run_demo.py
  validate_offline.py
  requirements.txt
```

## Why This Pattern

LangGraph state is excellent for the current run, but long-lived customer or
research context should not be copied through every graph checkpoint. This
example keeps graph state small and uses Memanto as the searchable, durable
layer that any future graph invocation can query.
