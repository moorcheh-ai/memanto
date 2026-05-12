# LangGraph + Memanto: Give Your Graph a Permanent Brain

A minimal LangGraph example that uses **Memanto** as a long-term,
cross-session memory layer — sitting *outside* of LangGraph's
thread-scoped `StateGraph` state.

> 30-second demo: _<add link to GIF / video here>_ — record your terminal
> running `python run_ingest.py` then `python run_recall.py` and drop the
> link in.

## What this demonstrates

- **Cross-session recall** — `run_ingest.py` stores a fact today.
  `run_recall.py`, started in a fresh process with **no LangGraph
  checkpoint and no shared thread state**, answers a question that
  can only come from yesterday's run. The only thing that crossed
  the boundary is the Memanto agent namespace.
- **Memory outside the graph state** — LangGraph's `StateGraph`
  state is ephemeral per thread. Memanto holds the persistent
  knowledge; the graph just calls `remember` / `recall` / `answer`
  tools.
- **Plain LangChain tools** — Memanto is exposed via
  `StructuredTool` instances, so the same wrappers also work with
  `create_react_agent`, custom routers, or `ToolNode`.

## Architecture

```
                 ┌─────────────────────────────────────────────┐
                 │              LangGraph StateGraph            │
                 │                                              │
   user turn ──► intake ─► recall ─► reason ─► remember ─► respond
                 │           │                    │             │
                 └───────────┼────────────────────┼─────────────┘
                             ▼                    ▼
                       memanto_recall      memanto_remember
                       memanto_answer
                             │                    │
                             └─────────┬──────────┘
                                       ▼
                          ┌────────────────────────┐
                          │   Memanto (Moorcheh)   │
                          │   agent_id namespace   │
                          │   - survives process   │
                          │   - survives threads   │
                          └────────────────────────┘
```

The `recall` and `remember` nodes are the only edges that leave the
graph. Everything else they do — checkpointing, semantic search,
type-aware storage — happens inside Memanto.

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys)
  (free tier: 100K ops/month)

No LLM key is required to run the example as-is. The `reason` node
is rule-based on purpose so the demo is deterministic and
zero-cost. Swap in any LangChain chat model when you want an
agentic loop.

## Setup

```bash
# 1. Clone the repo (if you haven't already)
git clone https://github.com/moorcheh-ai/memanto.git
cd memanto/examples/langgraph-memanto

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

## Cross-session demo (the bounty acceptance criterion)

This is the recommended flow to record for your video / GIF:

```bash
# Step 1 ("yesterday"): write a fact through LangGraph into Memanto.
python run_ingest.py

# Step 2 ("today"): start a brand-new process. LangGraph has zero
# thread state from step 1 — the only thing that survived is the
# Memanto namespace.
python run_recall.py
```

`run_recall.py` answers *"Who runs the support desk and what's the
response SLA?"* by pulling the fact through `memanto_recall` and
`memanto_answer`. The graph never sees yesterday's `StateGraph`
state — yet it still knows the answer.

You can also run both halves back-to-back in a single process:

```bash
python run_full_pipeline.py
```

Each `graph.invoke(...)` call gets its own fresh `GraphState`
(there's no checkpointer wired up), so even within one process
the second invocation only knows what Memanto told it.

## How LangGraph's thread state vs. Memanto compare

| Concern | LangGraph `StateGraph` | Memanto |
|---------|------------------------|---------|
| Lifetime | One thread / one run (or checkpoint TTL) | Permanent |
| Cross-process | No (unless a checkpointer is configured) | Yes |
| Cross-graph | No | Yes — any graph with the same `agent_id` |
| Search | Whatever you write into `state` | Semantic recall + RAG answer |
| Typing | TypedDict you define | 13 built-in semantic types + confidence |
| Cost at idle | N/A | Zero (serverless) |

Use both. LangGraph state is great for the current turn's working
memory; Memanto is great for everything you want the agent to know
tomorrow.

## How to plug Memanto into an existing LangGraph

### Before: an ephemeral graph

```python
from langgraph.graph import StateGraph

graph = StateGraph(MyState)
graph.add_node("reason", reason_node)
# ... edges ...
app = graph.compile()
# State dies when the thread ends.
```

### After: graph with a permanent brain

```python
from memanto.cli.client.sdk_client import SdkClient
from memanto_tools import MemantoSetup, create_memanto_tools

# 1. Boot Memanto (once per process)
setup = MemantoSetup(api_key="your-moorcheh-key")
client = setup.setup(agent_id="my-graph")

# 2. Build LangChain-compatible tools
tools = create_memanto_tools(client, agent_id="my-graph")

# 3. Use them inside nodes — they're just StructuredTools
def recall_node(state):
    found = tools["recall"].invoke({"query": state["user_input"], "limit": 5})
    return {"recalled": found}

def remember_node(state):
    tools["remember"].invoke({
        "memory_type": "fact",
        "title": "User goal",
        "content": state["user_input"],
    })
    return {}
```

The tools also work unchanged inside a LangGraph `ToolNode` or a
prebuilt `create_react_agent` if you'd rather have the LLM pick
when to remember.

## File structure

```
examples/langgraph-memanto/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
├── memanto_tools.py       # LangChain StructuredTool wrappers + MemantoSetup
├── graph.py               # StateGraph: intake → recall → reason → remember → respond
├── run_ingest.py          # Run 1: write a fact ("yesterday")
├── run_recall.py          # Run 2: prove cross-session recall ("today")
└── run_full_pipeline.py   # Both halves back-to-back in one process
```

## Troubleshooting

- **"MOORCHEH_API_KEY not set"** — copy `.env.example` to `.env`
  and fill in your key from
  [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys).
- **"No memories found for query"** on the recall run — make sure
  `run_ingest.py` finished without errors. Memanto writes are
  durable, but the activation step has to succeed.
- **Want to start over?** Just change `MEMANTO_AGENT_ID` in
  `.env` to a new value; you'll get a fresh namespace.

## Learn more

- [Memanto Documentation](https://docs.memanto.ai)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
