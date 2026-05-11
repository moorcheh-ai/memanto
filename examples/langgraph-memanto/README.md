# LangGraph + Memanto: Cross-Session Support Memory

This example shows a LangGraph support agent using Memanto as durable
long-term memory outside of LangGraph's per-run state.

The demo runs two independent sessions:

1. **Yesterday**: Dana from Acme says she prefers SMS updates and has an
   Enterprise two-hour SLA for checkout incidents. The graph stores those
   details in Memanto.
2. **Today**: Dana asks for an update on ticket `T-42`, but the current
   LangGraph thread does not include her preferences or SLA. The graph recalls
   those memories from Memanto and uses them in the response.

## 30-Second Demo

![LangGraph + Memanto demo](./assets/langgraph-memanto-demo.gif)

## What This Demonstrates

- **Cross-session recall**: the second run uses information absent from the
  current LangGraph state.
- **Memory outside graph state**: LangGraph carries transient workflow state;
  Memanto stores durable customer facts.
- **Typed memories**: preferences, facts, and commitments are stored with
  confidence and tags.
- **Testable fallback**: without a `MOORCHEH_API_KEY`, the example uses a small
  local JSON backend so the graph and docs can be verified without secrets.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ..\..
pip install -r requirements.txt
```

For real Memanto persistence, add your Moorcheh API key:

```bash
copy .env.example .env
# Edit .env and set MOORCHEH_API_KEY
```

## Run The Demo

Run both sessions with local storage:

```bash
python support_memory_agent.py --backend local --reset-local --session full
```

Run the real Memanto-backed flow:

```bash
python support_memory_agent.py --backend memanto --session full
```

You can also prove persistence across separate commands:

```bash
python support_memory_agent.py --backend memanto --session yesterday
python support_memory_agent.py --backend memanto --session today
```

## Example Output

```text
Session: yesterday (local-json)
Customer says: Hi, I am Dana from Acme. Please send SMS updates for ticket T-42...

Recalled long-term memories: 0
Agent response:
  I do not have durable customer context yet...

Stored new memories: 3
  - [preference] acme-dana prefers SMS updates for support tickets.
  - [fact] acme-dana is on an Enterprise support plan...

Session: today (local-json)
Customer says: Any update on ticket T-42? The checkout failure is still blocking launch.

Recalled long-term memories: 3
Agent response:
  I found durable customer context outside this LangGraph thread: use SMS
  updates and handle T-42 under the Enterprise two-hour SLA...
```

## File Structure

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- support_memory_agent.py
|-- test_support_memory_agent.py
`-- assets/langgraph-memanto-demo.gif
```

## Why This Pattern

LangGraph state is excellent for orchestrating a single run, but long-term
memory should survive restarts, new sessions, and different graph executions.
This example keeps those concerns separate:

- LangGraph nodes decide when to recall, respond, and persist facts.
- Memanto stores memories in a durable agent namespace.
- The graph remains deterministic enough to test locally while still using
  Memanto's real `remember` and `recall` APIs when configured.
