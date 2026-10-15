# Google ADK + Memanto: persistent long-term memory for ADK agents

A [Google ADK](https://google.github.io/adk-docs/) agent forgets everything when its session ends. ADK's built-in `InMemoryMemoryService` is lost on restart, and Vertex AI Memory Bank ties you to Google Cloud.

`memanto-google-adk` is a drop-in ADK memory service backed by [Memanto](https://github.com/moorcheh-ai/memanto):

| When | What happens |
|---|---|
| **A turn or session is saved** | New conversation events are turned into typed memories (preferences, facts, decisions, commitments...) by Memanto's extraction. Small talk is dropped. |
| **The agent needs context** | ADK's own `preload_memory` / `load_memory` tools recall this user's memories from Memanto, with type, confidence and date |
| **The user says something worth keeping** | The optional `memanto_remember` tool lets the agent save it immediately |

Everything lives in a Memanto agent, so you can read, edit and audit what your ADK agent knows with the Memanto CLI or web UI.

## Install

```bash
pip install memanto-google-adk
export MOORCHEH_API_KEY=...   # Memanto / Moorcheh key
```

## Use it

```python
import logging

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import preload_memory
from memanto_google_adk import MemantoMemoryService, remember_tool


async def save_to_memory(callback_context):
    # Store what is new in this session after every agent turn. If Memanto is
    # unreachable, log it rather than fail the user's turn: the next
    # successful save picks up the turns this one missed.
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        logging.exception("Saving to Memanto failed")


agent = LlmAgent(
    name="travel_agent",
    model="gemini-2.5-flash",
    instruction="You are a travel assistant.",
    tools=[preload_memory, remember_tool],
    after_agent_callback=save_to_memory,
)

runner = Runner(
    app_name="travel",
    agent=agent,
    session_service=InMemorySessionService(),
    memory_service=MemantoMemoryService(),
)
```

- **`preload_memory`** recalls memories that match the user's message and adds them to every request. Use **`load_memory`** instead if the model should decide when to look things up.
- **`remember_tool`** is optional: memories are extracted from the saved session anyway, but the tool lets the agent save a fact the moment it hears it.
- **`after_agent_callback`** is where saving happens. Each call extracts only the events added since the last save, so calling it every turn does not store anything twice. Extraction is one LLM call per save; to keep it off the response path, you can run it as a background task instead.

### With `adk web` / `adk run`

Register the `memanto://` scheme in a `services.py`:

```python
from google.adk.cli.service_registry import get_service_registry
from memanto_google_adk import MemantoMemoryService

get_service_registry().register_memory_service("memanto", MemantoMemoryService.from_uri)
```

Where ADK looks for it depends on the command:

| Command | `services.py` goes in |
|---|---|
| `adk web --memory_service_uri memanto:// <agents_dir>` (also `adk api_server`) | `<agents_dir>/services.py`, the folder that contains your agent folders |
| `adk run --memory_service_uri memanto:// <agents_dir>/my_agent` | `<agents_dir>/my_agent/services.py` |

A `services.py` in the wrong folder fails at startup with `Unsupported memory service URI: memanto:`. Set `MOORCHEH_API_KEY` in the environment before starting.

`memanto://my-agent` uses the Memanto agent `my-agent` for every app, instead of one per app.

## How memory is scoped

- **One Memanto agent per ADK app**, named `adk-<app_name>` (Memanto agent IDs allow only letters, digits, `-` and `_`). Pass `agent_id=` to share one Memanto agent across several apps.
- **Each ADK user's memories are private.** Every memory is tagged `user-<sha256 of user_id>`, and recall filters by that tag. The service takes the user from ADK's session, never from the model, and checks every result against the tag again before returning it, so one user never sees another's memories.
- **Sessions are saved incrementally.** Stored memories carry a marker for the last event they covered. The next save extracts only later events, even from a different process, and a retried save stores nothing.

## API

| | |
|---|---|
| `MemantoMemoryService(api_key=None, *, agent_id=None, recall_limit=10, extract_max_memories=20)` | The memory service. `api_key` defaults to `$MOORCHEH_API_KEY`. |
| `add_session_to_memory(session)` | Extracts and stores events added since the last save. |
| `add_events_to_memory(app_name=, user_id=, events=, session_id=None)` | Extracts and stores a delta, such as the latest turn. |
| `add_memory(app_name=, user_id=, memories=)` | Stores `MemoryEntry` items as they are, without extraction. `custom_metadata["type"]` sets the Memanto type (default `fact`). |
| `search_memory(app_name=, user_id=, query=)` | Semantic recall of this user's active memories. Each `MemoryEntry` has `timestamp`, and `custom_metadata` with `type`, `title`, `confidence`, `provenance`, `tags` and `score`. |
| `remember_tool` / `memanto_remember` | ADK tool: `memanto_remember(content, memory_type)`. |

## Limits

- **One active session per Memanto agent.** Activating an agent signs out every other client of that agent. Several processes serving the same app will take turns re-activating (the service retries once on a session error), which works but adds latency. For multi-worker deployments, prefer one worker per agent.
- Tool calls and tool results are not extracted, only user and agent text.
