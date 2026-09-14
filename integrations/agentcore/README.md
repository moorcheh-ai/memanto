# Amazon Bedrock AgentCore Runtime + Memanto

Persistent memory for [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html) agents using Memanto — the same **recall → execute → retain** pattern as [Hindsight’s AgentCore integration](https://hindsight.vectorize.io/sdks/integrations/agentcore).

AgentCore Runtime sessions are **ephemeral**: they terminate on inactivity and reprovision fresh environments. Memanto stores memory in a stable **agent namespace** keyed by validated user identity, not by `runtimeSessionId`, so context survives session churn.

> **Status:** Documentation and a **preview adapter** live in this folder. Run the tests below before publishing a standalone `memanto-agentcore` package to PyPI.

## How it works

```
AgentCore Runtime invocation
        │
        ▼
   before_turn()         ← Memanto recall (semantic search)
        │
        ▼
  Agent executes          ← Prompt enriched with prior context
        │
        ▼
   after_turn()          ← Memanto remember (async by default)
```

Default Memanto agent id (analogous to Hindsight’s memory bank):

```
tenant-{tenant_id}-user-{user_id}-agent-{agent_name}
```

Only `[A-Za-z0-9_-]` are allowed in Memanto agent ids; colons from other systems are normalized to underscores/hyphens.

## Installation (preview)

From the Memanto repo (until PyPI package ships):

```bash
pip install memanto
# Adapter code: integrations/agentcore/memanto_agentcore
```

Set your Moorcheh API key (same as CLI):

```bash
export MOORCHEH_API_KEY=your_key
```

## Quick start

```python
import os
from memanto.cli.client.sdk_client import SdkClient
from memanto_agentcore import MemantoRuntimeAdapter, TurnContext

client = SdkClient(api_key=os.environ["MOORCHEH_API_KEY"])
adapter = MemantoRuntimeAdapter(client, agent_name="support-agent")


async def handler(event: dict) -> dict:
    context = TurnContext(
        runtime_session_id=event["sessionId"],
        user_id=event["userId"],  # from validated auth — never client-supplied
        agent_name="support-agent",
        tenant_id=event.get("tenantId"),
        request_id=event.get("requestId"),
    )

    return await adapter.run_turn(
        context=context,
        payload={"prompt": event["prompt"]},
        agent_callable=run_my_agent,
    )


async def run_my_agent(payload: dict, memory_context: str) -> dict:
    prompt = payload["prompt"]
    if memory_context:
        prompt = f"Past context:\n{memory_context}\n\nCurrent request: {prompt}"

    output = await call_bedrock(prompt)
    return {"output": output}
```

## Lower-level hooks

```python
memory_context = await adapter.before_turn(context, query=user_message)

result = await run_my_agent(payload, memory_context=memory_context)

await adapter.after_turn(context, result=result["output"], query=user_message)
```

## Identity and auth

**Never use `runtimeSessionId` as the Memanto agent id.** Sessions expire; memory must not.

Preferred identity sources (in order):

1. Validated user ID from AgentCore JWT/OAuth context  
2. `X-Amzn-Bedrock-AgentCore-Runtime-User-Id` header  
3. Application-supplied user ID in trusted server-side deployments  

If `user_id` is missing, the default resolver raises `AgentResolutionError` (fail closed — no cross-user leakage).

## Custom agent id resolution

```python
from memanto_agentcore import MemantoRuntimeAdapter, TurnContext


def my_resolver(context: TurnContext) -> str:
    return f"acme_{context.user_id}_{context.agent_name}"


adapter = MemantoRuntimeAdapter(client, agent_id_resolver=my_resolver)
```

## Retrieval and retention

| Concern | Memanto behavior |
|--------|-------------------|
| Recall | Semantic search via `SdkClient.recall()` (typed memories, confidence, tags) |
| RAG-style answers | Optional: call `client.answer()` inside your agent instead of raw recall |
| Retention | Turn stored as `event` with tags `agentcore`, `turn` (configurable on adapter) |
| Async retention | Default `retain_async=True` — retention runs in a background task |

For complex planning steps you can increase `recall_limit` on `MemantoRuntimeAdapter` or run a dedicated recall query before routing.

## Failure modes

| Failure | Behavior |
|--------|----------|
| Memanto unavailable | `before_turn()` returns `""`, agent continues |
| Recall error | Logged warning, empty context |
| Retain failure | Logged warning, user turn unaffected |
| Missing `user_id` | `AgentResolutionError` at resolve time |

## Memanto vs Hindsight on AgentCore

| | Hindsight AgentCore | Memanto AgentCore (this pattern) |
|--|---------------------|----------------------------------|
| Stable key | Memory bank string | Memanto `agent_id` |
| Recall API | Hindsight recall / reflect | Memanto semantic `recall` |
| Memory model | Bank documents | 13 typed memory types + provenance |
| Package | `hindsight-agentcore` on PyPI | Preview: `integrations/agentcore` |

Both integrations target the same runtime constraint: **ephemeral sessions, durable user memory.**

## Test before implementing in production

### Recommended: full smoke script (real API)

One command runs retain → recall → `run_turn` → user-isolation check. No `PYTHONPATH` needed.

**PowerShell (Windows):**

```powershell
cd "c:\Users\patel\Downloads\Edge AI\memanto"
pip install -e .
$env:MOORCHEH_API_KEY = "your-moorcheh-api-key"
python integrations\agentcore\scripts\smoke_test.py
```

If you already ran `memanto` and have `~/.memanto\.env`, you can omit setting the env var.

**Expected output:** four steps ending with `PASS — AgentCore-style smoke test completed.` Exit code `0`.

**If recall retries fail:** wait a minute and re-run; cloud indexing can lag a few seconds.

### Unit tests (no API key)

```powershell
cd "c:\Users\patel\Downloads\Edge AI\memanto\integrations\agentcore"
$env:PYTHONPATH = "memanto_agentcore;c:\Users\patel\Downloads\Edge AI\memanto"
python -m pytest tests\test_adapter.py -q
```

### Pytest live smoke (same flow as script)

```powershell
cd "c:\Users\patel\Downloads\Edge AI\memanto\integrations\agentcore"
$env:PYTHONPATH = "memanto_agentcore;c:\Users\patel\Downloads\Edge AI\memanto"
python -m pytest tests\test_adapter_live.py -q
```

### 3. Manual CLI cross-check

```bash
memanto agent create tenant-acme-user-u42-agent-support-agent
memanto remember "User prefers email support" --type preference --source agentcore-runtime
memanto recall "support channel preference"
```

## Requirements

- Python 3.10+
- `memanto` with valid `MOORCHEH_API_KEY`
- AgentCore Runtime handler (async recommended)

## Related docs

- [Agent Integration Guide](../../docs/AGENT_INTEGRATION_GUIDE.md)
- [LangGraph integration](../langgraph/README.md) — similar recall/remember nodes
- [Session architecture](../../docs/SESSION_ARCHITECTURE.md)
