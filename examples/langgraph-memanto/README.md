# 🧠 LangGraph + Memanto — Permanent Agent Brain

Give your LangGraph agent a memory that **survives across sessions, restarts, and deployments**.

```
Session A (any time):   Agent researches → stores facts → Memanto
Session B (days later): NEW Python process → recall_node auto-loads → agent answers from memory
```

> **Core principle**: LangGraph handles orchestration and execution state extremely well.
> Memanto complements LangGraph by providing durable semantic memory across independent graph executions.
> **Checkpoint state and semantic memory solve different problems.**

## 🎬 Demo Video

▶️ **[Watch 30-second demo](https://www.loom.com/share/13bdd3d530934f529ae25cb3bf655da7)**

*Session A stores facts → Session B (completely new Python process) auto-recalls via `recall_node`*

## 📣 Social Posts

- 🐦 X/Twitter: <https://x.com/chidinmaonyenwe/status/2054728913558077858>
- 🤖 Reddit: *(post coming soon)*

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                LangGraph StateGraph                      │
│                                                         │
│  [START] → recall_node → agent_node ⇄ tools_node       │
│                 ↑                         |             │
│                 └─────────────────────────┘             │
│                                                         │
│  recall_node : auto-loads Memanto context at startup    │
│  agent_node  : ChatOpenAI + Memanto tools bound         │
│  tools_node  : ToolNode executing remember/recall/answer│
│                                                         │
│  StateGraph(AgentState) with conditional_edges          │
│  Typed state with add_messages reducer — current session only           │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (tools only)
           ┌───────────▼───────────┐
           │   Memanto Server      │  ← sole long-term memory store
           │  (memanto serve)      │  ← NOT used as LangGraph checkpoint
           └───────────┬───────────┘
                       │ SDK calls
           ┌───────────▼───────────┐
           │    Moorcheh.ai        │
           │  Zero-Index Semantic  │
           └───────────────────────┘
```

**Why tools-only (not a custom checkpointer/store)?**

Many native memory integrations in agent frameworks rely on embedding-oriented retrieval layers
where the original natural-language query may not be preserved cleanly through the abstraction boundary.
Memanto performs semantic retrieval directly from natural-language text queries via Moorcheh's
information-theoretic engine. Tool-based integration allows direct natural-language queries to Memanto and lets the LLM
choose the correct memory type from Memanto's 13 semantic types.

**Memanto is NOT used as LangGraph checkpoint state.** Checkpoint state manages execution recovery.
Memanto manages durable semantic memory. They are complementary, not competing.

---

## Quick Start

```bash
pip install -r requirements.txt

export MOORCHEH_API_KEY=mk-...
export OPENAI_API_KEY=sk-...
memanto serve

# Offline demo (no server/LLM needed)
python run.py --mock

# Session A: agent stores findings
python run.py --session research --namespace my-agent

# Session B: NEW Python process — agent recalls automatically
python run.py --session recall --namespace my-agent

# Interactive chat
python run.py --session chat
```

---

## Cross-Session Recall — How It's Proven

```
Session A  (python run.py --session research)
─────────────────────────────────────────────
👤 "Research quantum computing error correction"
🤖 calls remember_fact(...)   → mem_a1b2c3 stored in Memanto
👤 "I prefer bullet summaries"
🤖 calls remember_preference(...) → mem_d4e5f6 stored

         ↓  terminate process entirely  ↓

Session B  (python run.py --session recall)   ← NEW Python process
──────────────────────────────────────────────────────────────────
[recall_node runs automatically at graph startup]
📚 Loaded from Memanto: "surface codes require ~1000 qubits..."
📚 Loaded from Memanto: "user prefers bullet summaries"

👤 "What were we working on?"
🤖 "Based on our previous sessions: quantum error correction..."
```

**The recall session is a completely new Python process with a fresh LangGraph state.
No in-memory state is shared between runs.
All recalled information originates exclusively from Memanto persistence.**

---

## Contradiction Handling

Contradictions are resolved by storing the corrected fact as a new memory via the
documented `POST /remember` endpoint with `correction=True` metadata.
The previous fact is preserved in `metadata.previous_content` for full audit trail.

```python
# Old fact in Memanto: "~1000 physical qubits per logical qubit"
# New research found: ~100 qubits with new codes

correct_memory(
    old_content="~1000 physical qubits per logical qubit",
    new_content="~100 physical qubits per logical qubit (Google 2025)"
)
# New memory stored with metadata.previous_content = old fact
# Applications can inspect metadata.previous_content to resolve conflicts
```

---

## LangGraph Integration Details

```python
# StateGraph with typed state
workflow = StateGraph(AgentState)  # AgentState: TypedDict with add_messages reducer

# Nodes
workflow.add_node("recall", recall_node)   # auto-loads Memanto context
workflow.add_node("agent",  agent_node)    # LLM + bound tools
workflow.add_node("tools",  tool_node)     # ToolNode(MEMANTO_TOOLS)

# Edges with conditional routing
workflow.add_edge(START, "recall")
workflow.add_edge("recall", "agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")   # loop until no more tool calls
```

---

## Memory Types Used

| Type | When used |
|------|-----------|
| `fact` | Research findings, data points |
| `preference` | User style, format preferences |
| `decision` | Key conclusions, chosen approaches |
| `observation` | General agent notes |

---

## Project Structure

```
langgraph-memanto/
├── memanto_client.py   # Memanto v2 REST client (documented endpoints only)
├── tools.py            # LangGraph tools: remember/recall/correct/answer
├── graph.py            # StateGraph: recall_node → agent ⇄ ToolNode
├── run.py              # CLI: --mock / --session research|recall|chat
├── requirements.txt
└── README.md
```

---

## Memanto API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2/agents` | POST | Create agent namespace |
| `/api/v2/agents/{id}/activate` | POST | Start session → token |
| `/api/v2/agents/{id}/remember` | POST | Store memory (facts, preferences, corrections) |
| `/api/v2/agents/{id}/recall` | GET | Semantic search (natural language query) |
| `/api/v2/agents/{id}/answer` | POST | RAG answer over stored memories |
