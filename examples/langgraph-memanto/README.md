# LangGraph + Memanto Example

This example shows a LangGraph support workflow using Memanto as the long-term
memory layer. The first graph run stores customer facts and preferences. A later
graph run starts from a fresh graph instance, recalls those memories through
Memanto, and answers with the saved context.

## What this demonstrates

- A LangGraph workflow with explicit `recall_context`, `draft_response`, and
  `store_learning` nodes.
- Persistent customer memory through Memanto's `SdkClient`.
- A dry-run mode that lets reviewers run the flow locally before configuring a
  Moorcheh API key.
- Cross-session behavior: session 2 remembers the user's name, workspace,
  concise-response preference, and invoice issue from session 1.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

To use real Memanto persistence, set `MOORCHEH_API_KEY` in `.env`.

## Run the demo

```bash
python run_demo.py
```

If no API key is configured, the example automatically uses local dry-run
memory:

```bash
python run_demo.py --dry-run
```

Expected output:

```text
== Session 1: capture long-term context ==
User: My name is Dana. I prefer concise updates. I use the Acme workspace and need help with invoice exports.
Agent: Hi there, I checked long-term memory before answering...
Recalled memories: 0
Stored memories: 4

== Session 2: recall context in a fresh graph run ==
User: Can you continue helping with my invoice export?
Agent: Hi Dana, I found your saved context in the Acme workspace. I will keep this short...
Recalled memories: 4
Stored memories: 1
```

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
|-- .env.example
|-- memory_adapter.py
|-- support_agent.py
`-- run_demo.py
```

## Demo recording

For the bounty submission, record this command for the 30-second walkthrough:

```bash
python run_demo.py --dry-run
```

The dry-run path is intentionally deterministic so the recording is stable. The
same code path switches to Memanto when `MOORCHEH_API_KEY` is present.
