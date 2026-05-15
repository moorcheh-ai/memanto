# LangGraph + Memanto Persistent Support Agent

This example shows a LangGraph support agent using Memanto as its long-term
memory layer. The agent stores customer preferences in one session, then recalls
them from a fresh process in a later session.

![Cross-session recall demo](demo.gif)

The graph is intentionally small and practical:

1. `recall_context` retrieves relevant customer history from Memanto.
2. `draft_reply` uses that memory to decide how to answer.
3. `extract_memories` detects new preferences from the current message.
4. `persist_memories` writes those preferences back to Memanto.

## What It Proves

- Cross-session recall: session two remembers facts stored by session one.
- LangGraph owns the workflow state.
- Memanto owns durable memory outside the LangGraph state object.
- No external LLM key is required for the demo path, so the behavior is easy to
  record and verify.

## Quick Demo Without Credentials

The dry-run mode writes to `.memanto-demo-store.json`. It mirrors the Memanto
client shape so you can record the flow before connecting a real server.

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run_cross_session_demo.py
```

Expected session two output includes the remembered SMS and concise-reply
preferences even though it runs as a new graph invocation.

## Run Against Memanto

Start Memanto in another terminal:

```bash
memanto serve
```

Then edit `.env`:

```text
MEMANTO_DRY_RUN=0
MEMANTO_BASE_URL=http://127.0.0.1:8000
MEMANTO_AGENT_ID=langgraph-support-agent
```

Run the two sessions separately:

```bash
python seed_session.py
python run_support_session.py
```

## Files

- `memanto_client.py`: HTTP client for Memanto plus a JSON dry-run fallback.
- `support_agent.py`: LangGraph state machine and memory integration.
- `seed_session.py`: first session, stores customer preferences.
- `run_support_session.py`: second session, recalls those preferences.
- `run_cross_session_demo.py`: one-command demo for recording a short video.
