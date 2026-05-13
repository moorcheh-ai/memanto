# LangGraph + Memanto Persistent Memory Example

This example shows a LangGraph support agent using Memanto as durable memory.
The first graph run stores customer context in Memanto. A later graph run recalls
that context and uses it to answer a follow-up support question.

It is intentionally deterministic: no LLM key is required to understand or test
the integration. The focus is the LangGraph state flow and the Memanto memory
adapter.

## What This Demonstrates

- **LangGraph state orchestration**: recall, classify, store, and respond nodes
  are wired as a repeatable graph.
- **Durable Memanto memory**: customer preferences are stored through
  `SdkClient.remember` and retrieved later through `SdkClient.recall`.
- **Cross-run persistence**: run `--mode seed` first, then `--mode follow-up` in
  a new process to prove the second turn can use the first turn's memory.
- **Credential-free preview**: `--preview` uses a local JSON store with the same
  adapter shape, so reviewers can inspect the graph without an API key.

## Architecture

```text
support request
      |
      v
LangGraph: recall_customer_context
      |
      v
LangGraph: classify_request
      |
      v
LangGraph: store_memory
      |
      v
LangGraph: draft_response
      |
      v
support answer with remembered context
```

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- run_demo.py
`-- demo_transcript.md
```

## Setup

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

For the real Memanto-backed run, edit `.env` and set:

```bash
MOORCHEH_API_KEY=your_moorcheh_api_key_here
MEMANTO_AGENT_ID=langgraph-support-memanto-demo
```

## Run The Preview Demo

Preview mode requires no external credentials. It still executes the LangGraph
nodes and persists memory across separate Python processes using a local JSON
file.

```bash
python run_demo.py --mode seed --preview
python run_demo.py --mode follow-up --preview
```

Or run both turns:

```bash
python run_demo.py --mode full --preview
```

Expected output is captured in [demo_transcript.md](demo_transcript.md).

## 30-Second Demo

![LangGraph + Memanto demo](demo.gif)

## Run With Memanto

After setting `MOORCHEH_API_KEY`, run the same two turns without `--preview`:

```bash
python run_demo.py --mode seed
python run_demo.py --mode follow-up
```

The first command:

1. Creates or reuses the `langgraph-support-memanto-demo` Memanto agent.
2. Activates a Memanto session.
3. Stores ACME's deployment and communication preferences.

The second command:

1. Starts a new graph run.
2. Recalls ACME's stored preferences from Memanto.
3. Drafts a support answer that recommends the hosted deployment path, mentions
   SOC 2 compliance, and preserves the async email update requirement.

## Why This Pattern Is Useful

LangGraph is strong at explicit control flow. Memanto adds persistent semantic
memory to that flow without making every graph node responsible for storage
details. The adapter in `run_demo.py` keeps the memory boundary small:

- graph nodes ask for `memory.recall(customer, query)`
- graph nodes store structured memory through `memory.remember(memory_record)`
- the Memanto implementation owns agent setup, session activation, tags, and
  provenance

That lets the same graph logic support local preview, tests, and production
Memanto memory with minimal code changes.
