# Amazon Bedrock AgentCore Runtime + Memanto

Persistent memory for [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html) agents using Memanto — **recall → execute → retain** on each handler turn.

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

Default Memanto agent id:

```
tenant-{tenant_id}-user-{user_id}-agent-{agent_name}
```

Only `[A-Za-z0-9_-]` are allowed in Memanto agent ids. The readable form above is used only when it maps back to exactly one `(tenant_id, user_id, agent_name)`: every part already fits that charset and the `-user-` / `-agent-` delimiters appear exactly once. Any other identity (emails, dotted or non-Latin usernames, parts that contain a delimiter, or ids longer than 64 characters) maps to a SHA-256 hex id of the three parts instead. Two different identities never share a namespace. Without a tenant, the tenant part is `default`, so an explicit `tenant_id="default"` is the same scope as no tenant.

> **Upgrading from 0.1.0:** earlier versions rewrote unsupported characters to `_`. Different users could then resolve to the same agent id, for example `john.doe@acme.com` and `john_doe@acme.com`, or any two non-Latin names. Identities like these now get their own hashed agent id and start with empty memory. Their old agent is **not** adopted automatically, because it may hold memories from more than one person. Ids that were already unambiguous (e.g. `tenant-acme-user-u42-agent-support`, UUID user ids) are unchanged.

## Installation (preview)

From the Memanto repo (until PyPI package ships):

```bash
pip install -e .   # from Memanto repo root
pip install -e integrations/agentcore
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

If `user_id` is missing or blank, `resolve_agent_id()` raises `AgentResolutionError` before any custom or default resolver runs (fail closed — no cross-user leakage).

## Custom agent id resolution

```python
import hashlib
import json

from memanto_agentcore import MemantoRuntimeAdapter, TurnContext


def my_resolver(context: TurnContext) -> str:
    # Must be injective: never join raw identity parts with a character they
    # may contain ("a_b" + "c" and "a" + "b_c" would share one namespace).
    identity = json.dumps([context.tenant_id, context.user_id, context.agent_name])
    return "acme-" + hashlib.sha256(identity.encode()).hexdigest()[:48]


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
