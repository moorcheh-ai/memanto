# AG2 (AutoGen) + Memanto

Persistent long-term memory for [AG2](https://github.com/ag2ai/ag2) agents via Memanto — **remember → recall → answer** tools your assistant can call during chat.

> **Status:** Preview package in this folder. Run unit tests before relying on it in production.

## Features

- **Drop-in tools** — `register_memanto_tools()` registers remember, recall, and answer in one call
- **AG2-native** — Plain functions with `Annotated` type hints for `@register_for_llm` / `@register_for_execution`
- **GroupChat** — Register the same `agent_id` on multiple assistants; one executor runs tool calls
- **Selective tools** — `include_remember`, `include_recall`, `include_answer`
- **Shared namespace** — One Memanto `agent_id` per team or app

## Installation (preview)

From the Memanto repo:

```bash
pip install -e .                      # repo root → memanto
pip install -e integrations/ag2       # memanto-ag2
pip install "memanto-ag2[ag2]"        # optional: AG2 runtime for examples
```

> **Package name:** install **`ag2`** (AI agents), not **`a2g`** (unrelated bioinformatics tool).  
> **Version:** use **`ag2>=0.9,<1`** — `ag2` 1.x is a new framework; this integration uses `from autogen import AssistantAgent` (0.9.x).

Set your Moorcheh API key:

```bash
export MOORCHEH_API_KEY=your_key
```

## Quick start

```python
import os
from autogen import AssistantAgent, UserProxyAgent
from memanto.cli.client.sdk_client import SdkClient
from memanto_ag2 import openai_llm_config, register_memanto_tools

llm_config = openai_llm_config("gpt-4o-mini")

assistant = AssistantAgent(
    name="assistant",
    llm_config=llm_config,
    system_message="You are a helpful assistant with long-term memory.",
)
user_proxy = UserProxyAgent(name="user", human_input_mode="NEVER")

client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
register_memanto_tools(
    assistant,
    executor=user_proxy,
    client=client,
    agent_id="my-ag2-team",
)

user_proxy.initiate_chat(
    assistant,
    message="Remember that I prefer Python over JavaScript.",
)
```

## GroupChat with shared memory

```python
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, LLMConfig
from memanto_ag2 import register_memanto_tools

# ... LLMConfig + agents ...

executor = UserProxyAgent(name="executor", human_input_mode="NEVER")
for agent in [researcher, writer]:
    register_memanto_tools(agent, executor=executor, client=client, agent_id="team-memory")

group_chat = GroupChat(agents=[researcher, writer, executor], messages=[])
manager = GroupChatManager(groupchat=group_chat)
```

## Tool mapping

| AG2 tool (this package) | Memanto SDK | Role |
|-------------------------|-------------|------|
| `memanto_remember` | `remember()` | Store typed, tagged memories |
| `memanto_recall` | `recall()` | Semantic search |
| `memanto_answer` | `answer()` | RAG-style synthesis over stored memories |

## Configuration

```python
from memanto_ag2 import configure, register_memanto_tools

configure(source="ag2-prod", recall_limit=15)

register_memanto_tools(assistant, executor=executor, agent_id="my-bank")
```

## Tests

### Unit tests (no API key)

From the repository root (after `pip install -e .` and `pip install -e integrations/ag2`):

```bash
python -m pytest integrations/ag2/tests/test_tools.py -q
```

### Live smoke script (real API)

From the repository root (no `PYTHONPATH` needed):

```bash
export MOORCHEH_API_KEY=your-moorcheh-api-key
python integrations/ag2/scripts/smoke_test.py
```

Optional Step 6 runs a real AG2 chat when `OPENAI_API_KEY` is set and `ag2` is installed.

**Expected:** steps 1–5 pass, ending with `PASS — AG2 Memanto smoke test completed.` Exit code `0`.

### Pytest live smoke

From the repository root:

```bash
export MOORCHEH_API_KEY=your-moorcheh-api-key
python -m pytest integrations/ag2/tests/test_tools_live.py -q
```

## Requirements

- Python 3.10+
- `memanto` with valid `MOORCHEH_API_KEY`
- AG2 >= 0.9.0 for runtime examples (`pip install ag2`)

## Related

- [LangGraph integration](../langgraph/README.md)
- [AgentCore integration](../agentcore/README.md)
- [Agent Integration Guide](../../docs/AGENT_INTEGRATION_GUIDE.md)
