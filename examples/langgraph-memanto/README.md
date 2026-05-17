# LangGraph + Memanto: Persistent Memory for Agent Workflows

This example demonstrates how to integrate **Memanto** as a persistent, queryable
memory layer inside a **LangGraph** state graph.

## What It Shows

| Concept | How It's Used |
|---------|---------------|
| `remember()` | Store research findings as typed memories with confidence scores |
| `recall(topic)` | Semantic search across stored memories before re-researching |
| `answer(question)` | RAG-based answer generation from the memory store |
| LangGraph `StateGraph` | Routing between memory-check, research, storage, and answer nodes |
| Cross-session persistence | Run the same query twice — the second run uses stored memories |

## Architecture

```
                    ┌──────────────┐
                    │   check_     │  ← recall(topic): query existing knowledge
                    │   memory     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   router     │  ← conditional: research or answer?
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │                         │
     ┌────────▼────────┐      ┌─────────▼─────────┐
     │  research_topic │      │  answer_question   │ ← answer(question): RAG
     │  (LLM generates │      └─────────┬──────────┘
     │   findings)     │                │
     └────────┬────────┘                │
              │                         │
     ┌────────▼────────┐                │
     │  store_findings │ ← remember()   │
     └────────┬────────┘                │
              │                         │
              └────────────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │     END      │
                    └──────────────┘
```

## Prerequisites

- **Python** 3.10+
- A **Moorcheh API key** (free tier: 100K operations/month)
  → Get one at [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys)
- An **OpenRouter API key** (free tier available for the LLM research node)
  → Get one at [openrouter.ai/keys](https://openrouter.ai/keys)

## Setup

```bash
# 1. Create a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
cp .env.example .env
# Edit .env and fill in your MOORCHEH_API_KEY and OPENROUTER_API_KEY
```

## Run the Demo

```bash
python run.py
```

### Expected output

The demo runs the same research query twice:

**Run 1** — No prior memories exist, so the agent:
1. `recall("economic impacts of LLMs")` → 0 hits
2. Routes to `research_topic` (LLM generates findings)
3. `remember()` stores 3+ findings as `fact`-type memories
4. `answer("economic impacts of LLMs")` → produces the final answer

**Run 2** — Memories from Run 1 persist, so the agent:
1. `recall("economic impacts of LLMs")` → finds stored memories
2. Routes directly to `answer()` without re-researching
3. Generates the answer from the stored memory context

```
▶  Run 1 — Query: What are the economic impacts of large language models?
   (No existing memories — agent will research and store)

   ... (research + remember + answer) ...

▶  Run 2 — Same query: What are the economic impacts of large language models?
   (Memories from run 1 should be found — agent goes straight to answer)

   ✅ Memory persistence confirmed! Found 3 existing memories.
```

## File Structure

```text
examples/langgraph-memanto/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
├── memory_client.py       # Memanto client wrapper
├── research_assistant.py  # LangGraph StateGraph definition
└── run.py                 # Demo entry point
```

## How the LangGraph Workflow Works

### State (`AgentState`)

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    topic: str                     # Research question
    memory_hits: int               # Number of relevant memories found
    knowledge_sufficient: bool     # Router decision flag
    research_findings: str | None  # Raw LLM output
    final_answer: str | None        # Final answer
```

### Nodes

| Node | Function | Memanto API |
|------|----------|-------------|
| `check_memory` | Query existing knowledge about the topic | `recall(query, limit=5)` |
| `research_topic` | LLM generates research findings *(only if memory is insufficient)* | — |
| `store_findings` | Persist findings as typed memories | `remember(type="fact", ...)` |
| `answer_question` | Generate a final answer from stored context | `answer(question, limit=5)` |

### Edges

| Edge | Type | Condition |
|------|------|-----------|
| `START → check_memory` | Direct | Always |
| `check_memory → router` | Conditional | `knowledge_sufficient ? answer_question : research_topic` |
| `research_topic → store_findings` | Direct | Always |
| `store_findings → answer_question` | Direct | Always |
| `answer_question → END` | Direct | Always |

## Key Integration Points

### 1. Passing Memanto to nodes via closure

LangGraph node functions can close over the Memanto client instead of relying
on global state:

```python
def build_graph(memory: MemantoMemory) -> StateGraph:
    builder = StateGraph(AgentState)
    builder.add_node("check_memory", lambda s: check_memory(s, memory))
    ...
```

### 2. `recall()` as a semantic gate

The `check_memory` node queries Memanto's semantic search. If enough relevant
memories are found, the graph skips the expensive research step:

```python
def check_memory(state, memory):
    results = memory.recall(query=state["topic"], limit=5)
    sufficient = len(results) >= 2
    return {"memory_hits": len(results), "knowledge_sufficient": sufficient}
```

### 3. `remember()` for typed persistence

Findings are stored as `fact`-type memories with confidence scores and tags,
making them independently retrievable and confidence-scorable:

```python
memory.remember(
    memory_type="fact",
    title="LLMs and economic productivity",
    content="... detailed finding ...",
    confidence=0.85,
    tags=["llm", "economics", "research"],
)
```

### 4. `answer()` for RAG-based responses

The final node uses Memanto's `answer()` method which performs retrieval-augmented
generation over the stored memory namespace:

```python
result = memory.answer(question=topic, limit=5)
final_answer = result.get("answer", "")
```

## Customising the Example

| Change | How |
|--------|-----|
| Different research topic | Modify the `topic` in `run.py` |
| Different memory threshold | Adjust the `hits >= 2` check in `check_memory()` |
| More memory recall results | Increase `limit` in `memory.recall()` |
| Use web search instead of LLM | Replace `research_topic` with a web search tool |
| Add more memory types | Use `observation`, `preference`, or `learning` types |
| Add a chat loop | Replace one-shot invoke with a `while True` loop |

## Troubleshooting

**`MOORCHEH_API_KEY is not set`**
→ Create a `.env` file with your key, or `export MOORCHEH_API_KEY=...`

**`AgentNotFoundError` during first run**
→ The example auto-creates the agent on first use. Check your API key has
   sufficient permissions.

**`research_topic` fails (OpenRouter/LLM error)**
→ Verify `OPENROUTER_API_KEY` in your environment. The example can still
   demonstrate `remember()` + `recall()` even without the LLM node if you
   pre-populate some memories via the Memanto CLI: `memanto remember ...`

## Resources

- [Memanto Documentation](https://docs.moorcheh.ai)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Moorcheh Console (API Keys)](https://console.moorcheh.ai/api-keys)
