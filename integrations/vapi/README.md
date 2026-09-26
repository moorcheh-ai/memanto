# Vapi + Memanto: give your voice agent a memory

A [Vapi](https://vapi.ai) assistant starts every call from zero. It doesn't know your company's policies unless they're in the prompt, and it makes the same mistake on Friday that it was corrected for on Monday.

`memanto-vapi` is one webhook that gives the assistant a memory it keeps:

| When | What happens |
|---|---|
| **Call starts** | Your knowledge and the lessons learned so far go into the prompt as `{{memanto_context}}` |
| **During the call** | The agent can look things up with `memanto_recall`, and save what it learns with `memanto_remember` |
| **Call ends** | The conversation is turned into lessons: mistakes it made, corrections it got, answers that worked, facts about the business |

Memory lives in one Memanto agent, so you can read, edit and audit everything it knows with the Memanto CLI or web UI.

## Two scopes: pick one

```
MEMANTO_VAPI_SCOPE=shared   # default
```
**shared** — one memory for the whole assistant: your organization's knowledge plus the lessons from every call. Every caller benefits from what the agent learned yesterday. Nothing personal about a caller is saved, so there is nothing to leak between callers.

```
MEMANTO_VAPI_SCOPE=caller
```
**caller** — everything above, and each caller also gets memories only they see: their preferences, their open issues, what you promised them. Their tag is an HMAC of their phone number (or `customer.externalId` for web and chat calls), keyed with a salt you set, so raw numbers are never stored.

In caller scope, the context has two parts:

```text
Knowledge and lessons learned:
- [instruction] Refund window: refunds are accepted within 30 days (2026-09-01)
- [error] Do not quote weekend hours as 9-5; they are 10-4 (2026-09-14)

About this caller:
- [preference] Prefers morning delivery slots (2026-08-02)
- [commitment] Promised a callback about invoice 4471 (2026-09-15)
```

**The server decides whose memories a call can read and write**, from the caller Vapi reports. The model never passes a caller ID, so a prompt injection cannot reach another caller's memories, and every result is checked again on our side before it is returned. In caller scope, whatever the agent saves mid-call is private to the caller it is talking to; shared lessons come only from end-of-call extraction, whose prompt excludes caller details.

## Install and run

```bash
pip install memanto-vapi

export MOORCHEH_API_KEY=...                  # Memanto / Moorcheh key
export MEMANTO_VAPI_AGENT_ID=acme-support    # Memanto agent for this assistant
export MEMANTO_VAPI_SECRET=$(openssl rand -hex 32)   # also goes in the Vapi credential
export MEMANTO_VAPI_ASSISTANT_ID=...         # your saved Vapi assistant (inbound calls)

# caller scope only:
# export MEMANTO_VAPI_SCOPE=caller
# export MEMANTO_VAPI_CALLER_SALT=$(openssl rand -hex 32)

memanto-vapi serve --port 8080
```

The webhook is at `POST /vapi/webhook`, with `GET /health` for status. It must be reachable over public HTTPS; for local testing use a tunnel such as `ngrok http 8080`.

The Memanto agent is created on first start. Run **one instance per agent**: Memanto keeps one active session per agent, so instances sharing `~/.memanto` would sign each other out.

> **Keep the salt secret and stable.** Changing it cuts every caller off from their existing memories.

## Load your knowledge into the agent

Anything in the Memanto agent is available to the voice agent. Add it with the CLI before starting the webhook (activating an agent elsewhere signs out a running webhook until its next call):

```bash
memanto agent activate acme-support
memanto remember "Refunds are accepted within 30 days of delivery" --type instruction
memanto upload handbook.pdf
```

You can also review and correct what the agent learned, in the same place:

```bash
memanto recall "weekend hours"
memanto edit <memory-id> --content "Weekend hours are 10-4"
```

## Configure Vapi

**1. Credential.** Create a **Bearer Token** credential whose token is `MEMANTO_VAPI_SECRET`. Requests without it get `401`. The legacy `X-Vapi-Secret` header also works.

**2. Tools.** Print the tool definitions and create each one with `POST https://api.vapi.ai/tool`:

```bash
memanto-vapi tools --server-url https://your-host/vapi/webhook --credential-id <credential id>
# add --scope caller if the webhook runs in caller scope
```

Then put both tool IDs in the assistant's `model.toolIds`.

**3. Assistant prompt.** Use the variable, and say when to save:

```text
What you know from earlier calls:
{{memanto_context}}

Use memanto_recall when you are unsure how to answer or handle a request.
Use memanto_remember when you are corrected, or you learn something that
would help on future calls.
```

**4. Server URL.** Point Vapi at the webhook with the credential:
- on the **phone number**, so inbound calls ask it which assistant to use. Don't also attach an assistant to the number.
- on the **assistant** (`server.url`), with `end-of-call-report` in `serverMessages`, so calls are learned from.

## Outbound, web, and chat calls

Vapi only sends `assistant-request` for inbound phone calls. For calls you start yourself, build the overrides when you create the call:

```python
from memanto.cli.client.sdk_client import SdkClient
from memanto_vapi import VapiMemory

memory = VapiMemory(SdkClient(api_key=...), agent_id="acme-support")

overrides = await memory.build_assistant_overrides({})
# caller scope: pass the person, e.g.
# await memory.build_assistant_overrides({"customer": {"number": "+15551234567"}})

# POST https://api.vapi.ai/call
#   {"assistantId": ..., "customer": ..., "assistantOverrides": overrides}
```

Tools and end-of-call learning work the same for these calls. In caller scope, the call must carry `customer.number` or `customer.externalId`; otherwise automatic end-of-call retention is skipped. Shared memories can still be recalled at call start, but memories inferred from a caller transcript are retained only for that caller.

## Mount in your own FastAPI app

```python
from fastapi import FastAPI
from memanto_vapi import VapiMemory, create_router

memory = VapiMemory(client, agent_id="acme-support")
app = FastAPI()
app.include_router(create_router(memory, secret=SECRET, assistant_id=ASSISTANT_ID))
```

`create_router` does not activate the Memanto session at startup the way `create_app` does. Call `memory.ensure_ready()` in your own startup hook, so the first caller doesn't wait for it.

## Behavior and limits

- **Memory never delays a call.** Vapi allows 7.5 seconds end to end for `assistant-request`; lookup is capped at `recall_timeout` (3s). On a timeout or error, the call starts with an empty `{{memanto_context}}` and a warning is logged.
- **Context is bounded** to `recall_limit` (10) recent and 10 relevant memories per section, and `max_context_chars` (4000) in total.
- **Learning happens after the response.** `end-of-call-report` is acknowledged immediately and processed in the background. Calls where nobody spoke are skipped.
- **Caller scope is fail-closed for automatic retention.** End-of-call memories inferred from caller-controlled transcripts are always tagged to that caller, and retention is skipped if the caller cannot be identified. Shared scope keeps its shared extraction behavior.
- **Retries are ignored.** End-of-call memories carry a `retained-<call id>` tag, so a webhook Vapi re-delivers is not learned from twice. Something can still be saved twice within one call — once by the tool while talking, once by extraction at the end.
- **Tags starting with `caller-` mark private memories.** Don't use that prefix for your own tags; shared lookups skip anything carrying one.
- **Conflict scans and daily summaries cover the whole agent**, including every caller's memories in caller scope.

## Tests

```bash
pip install -e ".[dev]"
pytest tests
```

The tests build payloads that follow Vapi's OpenAPI schema and use a fake Memanto client, so no network calls are made.
