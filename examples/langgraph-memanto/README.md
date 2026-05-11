# LangGraph + Memanto: Cross-Session Support Agent Memory

This example shows how to use Memanto as a long-term memory layer for a
LangGraph-style customer support agent. The graph can store durable memories in
one run and recall them in a later run even when the new graph state starts
empty.

## What It Demonstrates

- **Cross-session recall**: session 2 remembers a user's preference stored in
  session 1.
- **Memory outside graph state**: LangGraph state only carries the current
  ticket. Memanto owns durable user memory.
- **Documented adapter boundary**: the demo runs offline with an in-memory
  adapter and can be swapped to Memanto's `SdkClient` in real deployments.
- **Small, testable graph**: deterministic nodes make the example easy to run
  without external LLM keys.

## Scenario

The customer support agent handles two tickets for the same user:

1. Session 1: the user says they prefer short answers and email follow-up.
2. Session 2: the user opens a new ticket but does not repeat those preferences.

The second run retrieves the preferences from Memanto and uses them in the
response plan.

## Quick Start

```bash
cd examples/langgraph-memanto
pip install -r requirements.txt
python support_agent.py
```

Expected output:

```text
Session 1 stored memories:
- preference: User prefers concise support answers.
- preference: User prefers email follow-up.

Session 2 recalled memories:
- User prefers concise support answers.
- User prefers email follow-up.

Final response plan:
Use a concise tone and send the follow-up over email.
```

## Run The Test

```bash
python -m pytest test_support_agent.py
```

The test verifies that a fresh second graph state can still recall memories
written during the first session.

## Using The Real Memanto Client

The demo uses `InMemoryMemantoAdapter` so reviewers can run it without API keys.
For production usage, replace it with an adapter backed by
`memanto.cli.client.sdk_client.SdkClient`.

```python
from memanto.cli.client.sdk_client import SdkClient

client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
client.create_agent(agent_id="support-agent", pattern="tool")
client.activate_agent("support-agent")
```

The graph nodes only depend on three adapter methods:

- `remember(agent_id, memory_type, title, content, tags)`
- `recall(agent_id, query, limit)`
- `answer(agent_id, question)`

That boundary keeps LangGraph orchestration separate from the memory backend.

## Demo Recording

For the bounty video/GIF, record this sequence:

1. Run `python support_agent.py`.
2. Point to the "Session 1 stored memories" section.
3. Point to the "Session 2 recalled memories" section.
4. Show that session 2 starts with a new ticket and still uses session 1's
   preferences.

