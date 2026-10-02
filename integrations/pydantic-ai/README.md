# Pydantic AI + Memanto

Give a [Pydantic AI](https://ai.pydantic.dev) agent persistent, cross-session memory backed by Memanto.

## What it does

`memanto-pydantic-ai` connects a Pydantic AI agent to a Memanto agent in two complementary ways:

- **`memory_instructions`**: before each run, recalls the memories most relevant to the user's prompt and adds them to the agent's instructions, so the agent uses its memory even when the model doesn't think to look.
- **`create_memanto_tools`**: three tools the model calls explicitly:
  - `memanto_remember`: store a structured memory (fact, preference, decision, and 10 other types)
  - `memanto_recall`: search stored memories by natural-language query
  - `memanto_answer`: get a synthesized, RAG-grounded answer from stored memories

Memory lives in a real Memanto agent, so you can read, edit, and audit everything with the Memanto CLI or web UI.

## Install

Requires Python 3.10+. Installs `pydantic-ai-slim` 2.0+ and `memanto` 0.2.21+.

```bash
pip install memanto-pydantic-ai "pydantic-ai-slim[openai]"   # or the extra for your model provider, or full `pydantic-ai`
export MOORCHEH_API_KEY=your_key_xxxxxxxxxxxxxxxxxx
export OPENAI_API_KEY=sk-...  # for the openai:gpt-4o model below
```

## Use it

```python
from pydantic_ai import Agent

from memanto_pydantic_ai import MemantoSetup, create_memanto_tools, memory_instructions

setup = MemantoSetup()  # reads MOORCHEH_API_KEY
client = setup.setup(agent_id="travel-agent", description="Travel planning assistant")

agent = Agent(
    "openai:gpt-4o",
    instructions=[
        "You have long-term memory. Use memanto_remember to save durable facts, "
        "preferences, and decisions the user shares.",
        memory_instructions(client, agent_id="travel-agent"),
    ],
    tools=create_memanto_tools(client, agent_id="travel-agent"),
)

result = agent.run_sync("I always fly out of LAX, remember that for future trips.")
print(result.output)

# In a later session, the LAX preference is recalled and injected automatically:
result = agent.run_sync("Book me a flight to Tokyo.")
print(result.output)

setup.teardown("travel-agent")
```

Use either piece on its own: tools only (the model decides when to read memory), or `memory_instructions` only (read-only, automatic recall).

## How it behaves

- **Automatic recall runs once per run.** Pydantic AI re-evaluates instructions before every model request, so the recall result is cached for the rest of the run. The run's user prompt is the query (text parts only; truncated to 1000 characters), and only active, non-expired memories are injected.
- **A memory outage never takes your agent down.** If the automatic recall fails (network, auth, backend), a warning is logged and the run continues without injected memories. The tools still raise those errors, so failures are visible.
- **Bad tool calls are retried, not fatal.** The tools' limits are part of their schema (13 memory types, confidence 0.0–1.0, title up to 100 characters, recall limit 1–100). If the model still sends an invalid call, the error goes back to it as a retry prompt and it corrects the call.
- **Expired memories are labelled.** `memanto_recall` marks memories that are no longer current as `(expired)` and shows when each was saved.
- **Misconfiguration fails fast.** `create_memanto_tools` and `memory_instructions` raise a clear `ValueError` when the client has no active session for the `agent_id`, instead of failing on the model's first tool call.

## One client per Memanto agent

A Memanto client holds one session for one agent. To give each end user their own memory, use one Memanto agent per user, each with its own `MemantoSetup`:

```python
def agent_for(user_id: str) -> Agent:
    agent_id = f"travel-{user_id}"
    client = MemantoSetup().setup(agent_id)
    return Agent(
        "openai:gpt-4o",
        instructions=memory_instructions(client, agent_id=agent_id),
        tools=create_memanto_tools(client, agent_id=agent_id),
    )
```

Cache the result per user in a long-running app rather than calling `setup` on every request.

> **One session per agent:** activating a session invalidates any other session for the same Memanto agent (for example, one opened by the `memanto` CLI). Give each running app its own `agent_id`.

## API

`MemantoSetup(api_key=None)`: creates or reuses a Memanto agent and activates a session. Reads `MOORCHEH_API_KEY` when `api_key` is omitted.
- `.setup(agent_id, pattern="tool", description=None, duration_hours=6)` → an `SdkClient` with an active session for `agent_id`. Sessions renew automatically while in use.
- `.teardown(agent_id)`: deactivates the session.

`create_memanto_tools(client, agent_id, *, include_remember=True, include_recall=True, include_answer=True)` → `list[Tool]`, ready to pass into `Agent(tools=...)`. Set `include_remember=False` for a read-only agent.

`memory_instructions(client, agent_id, *, limit=5, min_similarity=None, prefix=...)` → a dynamic instruction, ready to pass into `Agent(instructions=...)`.
- `limit`: maximum memories to inject (1–100).
- `min_similarity`: minimum similarity (0.0–1.0); defaults to Memanto's configured recall threshold.
- `prefix`: text placed before the injected memories.

Memories saved through `memanto_remember` are tagged with source `pydantic-ai-agent` and provenance `explicit_statement`.

## Tests

```bash
pip install -e ".[dev]"
pytest tests
```

Tests use a mocked `SdkClient` and drive a real Pydantic AI agent with a scripted model, so no network calls are made.
