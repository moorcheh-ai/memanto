# LangGraph + Memanto Example

This example shows a LangGraph support workflow using **Memanto** as a
cross-session memory layer. LangGraph keeps the current request in state, while
Memanto stores and recalls customer preferences that survive separate terminal
runs.

## What this demonstrates

- Cross-session recall: run the writer today, recall the same memory tomorrow.
- Memory outside graph state: LangGraph state does not carry prior preferences.
- Typed memory: preferences are stored with tags, confidence, provenance, and source.
- Practical workflow: a support agent adapts answers to remembered customer needs.

## Demo

30-second GIF/video link: [demo.gif](demo.gif)

Suggested recording flow:

```bash
python run_store_memory.py
python run_recall_memory.py
```

The second command starts a new process and still recalls ACME's preferences
through Memanto.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env       # macOS/Linux
copy .env.example .env     # Windows
```

Edit `.env` and set your `MOORCHEH_API_KEY`.

For a local control-flow review without calling Memanto Cloud, set:

```bash
MEMANTO_DRY_RUN=1
```

## Run the cross-session demo

First store the preferences:

```bash
python run_store_memory.py
```

Then start a separate run that receives only the current request:

```bash
python run_recall_memory.py
```

Expected behavior:

- `run_store_memory.py` creates or activates `MEMANTO_AGENT_ID`.
- It stores ACME's support preferences in Memanto.
- `run_recall_memory.py` builds a LangGraph workflow.
- The graph recalls ACME memories from Memanto and drafts a response that uses
  the remembered style and timezone preferences.

## File structure

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── requirements.txt
├── memory_tools.py
├── graph.py
├── run_store_memory.py
└── run_recall_memory.py
```

## Why this uses Memanto instead of LangGraph state

LangGraph state is excellent for the current execution. The support preferences
in this example are intentionally stored in Memanto so they remain available to
future graph runs, separate processes, and separate agent sessions.
