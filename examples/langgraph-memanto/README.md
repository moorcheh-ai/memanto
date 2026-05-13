# LangGraph + Memanto Example

This example shows a small customer-support `StateGraph` that uses Memanto as
long-term memory outside the graph state. The graph recalls durable context at
the start of each run, drafts a response, then writes the current interaction
back to Memanto for future sessions.

## What This Demonstrates

- Cross-session recall: run `seed` today and `recall` later with the same
  `MEMANTO_LANGGRAPH_AGENT_ID`.
- Memory outside LangGraph state: the graph is compiled without a checkpointer,
  so durable context comes from Memanto, not an in-thread state snapshot.
- Typed memories: customer facts are stored with `fact` type, confidence, and
  tags for future semantic retrieval.
- Credential-free review path: `--backend preview --phase full` runs the same
  node logic with an in-memory adapter.

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- .env.example
|-- langgraph_memanto.py
|-- requirements.txt
|-- run_demo.py
`-- test_langgraph_memanto.py
```

## Setup

```bash
cd examples/langgraph-memanto
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set MOORCHEH_API_KEY.
```

## Quick Review Without Secrets

```bash
python run_demo.py --backend preview --phase full
```

The preview backend keeps memory in process, so it is only a local smoke test.
Use the Memanto backend below for the actual cross-session proof.

## Cross-Session Memanto Demo

Run these as two separate commands. The second command starts a fresh graph
invocation and recalls what the first command stored in Memanto.

```bash
python run_demo.py --backend memanto --phase seed
python run_demo.py --backend memanto --phase recall
```

Expected evidence in the second command:

- `Recalled memories: 1` or more
- the response mentions the customer's previously stored invoice or renewal
  context
- the same `MEMANTO_LANGGRAPH_AGENT_ID` appears in both runs

## How The Graph Works

```text
load_memanto_context -> draft_response -> write_followup_memory -> END
```

- `load_memanto_context` searches Memanto with the current customer and message.
- `draft_response` builds a deterministic support reply from recalled memories.
- `write_followup_memory` stores the current customer interaction for later
  sessions.

## PR Evidence Checklist

For the bounty PR, include:

- A transcript or screenshot of `python run_demo.py --backend preview --phase full`.
- A transcript or screenshot of the two separate Memanto commands above.
- A 30-second GIF or video link showing seed then recall.
- The social post link required by the issue, tagged with `#Memanto` and
  `@moorcheh-ai`.
