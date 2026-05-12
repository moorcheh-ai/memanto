# LangGraph + Memanto Example

This example shows a LangGraph support workflow using Memanto as long-term memory. The first run stores customer preferences, and a later run recalls them in a new session before drafting a reply.

![LangGraph + Memanto terminal proof](demo.gif)

It is designed for the bounty in issue #397:

- Cross-session recall
- Clean code in a single folder
- A 30-second terminal recording path
- A clear guide for swapping local LangGraph state for Memanto memory

## What the Graph Does

```text
load_ticket
  -> recall_customer_context
  -> choose_action
  -> store_profile_memories
  -> draft_reply
```

The important part is that `recall_customer_context` does not read from the current LangGraph state. It asks the memory backend for durable memories keyed by the same Memanto agent id. That means a new process can recover details from an earlier run.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd examples\langgraph-memanto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Quick Demo Without API Keys

Use the local JSON backend first. It proves the graph shape and the cross-process recall behavior without calling any external service.

```bash
python run_full_demo.py --backend local --reset-local
```

Or record the two sessions separately:

```bash
python run_store_profile.py --backend local
python run_recall_profile.py --backend local
```

Expected proof point in the second command:

```text
Session: session-2-recall
Stored memories: 0
Recalled memories: 3
Action: draft_concise_email_first_reply
```

## Run With Memanto

Create a Moorcheh API key, then run:

```bash
export MOORCHEH_API_KEY=...
export MEMANTO_LANGGRAPH_BACKEND=memanto
export MEMANTO_LANGGRAPH_AGENT_ID=langgraph-support-demo

python run_store_profile.py --backend memanto
python run_recall_profile.py --backend memanto
```

The Memanto backend uses this repository's `DirectClient` to:

1. Create or reuse a Memanto agent.
2. Activate a session.
3. Store typed memories with `remember`.
4. Recall relevant context with `recall`.

## How To Swap Standard LangGraph State For Memanto

Typical LangGraph examples keep all state inside the graph:

```python
state["customer_preferences"] = preferences
```

This only survives for the current run unless you add a checkpointer. In this example, durable memory lives behind a backend:

```python
backend.remember(
    agent_id="langgraph-support-demo",
    memory_type="preference",
    title="Ada prefers concise support replies",
    content="Customer ada-lovelace prefers concise, direct support replies.",
    tags=["ada-lovelace", "support", "tone"],
)
```

Later, a fresh graph run can retrieve context before deciding what to do:

```python
memories = backend.recall(
    agent_id="langgraph-support-demo",
    query="ada-lovelace preferences email concise support context",
    limit=5,
)
```

The graph remains stateless between runs, while Memanto supplies durable, typed, searchable memory.

## Recording Script

For a 30-second terminal recording:

```bash
rm -f .langgraph_memanto_memory.json
python run_store_profile.py --backend local
python run_recall_profile.py --backend local
```

Then repeat with `--backend memanto` after setting `MOORCHEH_API_KEY` if you want the recording to show the live Memanto backend.
