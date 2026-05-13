# LangGraph + Memanto Cross-Session Memory

This example adds a small LangGraph research mentor that uses Memanto as its
long-term memory layer.  LangGraph state only carries the current turn; durable
facts are stored and retrieved through the Memanto adapter in `memory_store.py`.

Issue covered: moorcheh-ai/memanto#397.

## What it demonstrates

- Cross-session recall: session A stores a research preference, session B starts
  as a fresh graph run and recalls it.
- Memanto outside graph state: graph nodes call `store.recall()` and
  `store.remember()` instead of keeping long-term context in LangGraph state.
- Live and preview modes: with `MOORCHEH_API_KEY`/`MEMANTO_API_KEY`, the adapter
  uses `SdkClient`; with `--preview`, reviewers can run the exact flow locally
  without credentials.
- Clean single-folder example: graph, memory adapter, demo runner, requirements,
  environment template, transcript, and demo GIF.

## Files

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── graph.py
├── memory_store.py
├── requirements.txt
├── run_demo.py
├── transcript.txt
└── demo.gif
```

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For live Memanto storage:

```bash
cp .env.example .env
export MOORCHEH_API_KEY=your_key_here
python run_demo.py --mode full
```

For credential-free review:

```bash
python run_demo.py --mode full --preview --reset
```

## Expected output

The first run stores a memory:

```text
SESSION A — store durable research context
Stored memory id: offline-1
```

The second run recalls that memory in a new LangGraph invocation:

```text
SESSION B — new graph run, recall durable context
Durable Memanto context used:
- Research preference captured by LangGraph: Ava is researching privacy-preserving AI assistants and prefers concise implementation checklists.
```

## Demo

![LangGraph + Memanto cross-session memory demo](demo.gif)
