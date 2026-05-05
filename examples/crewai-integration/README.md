# CrewAI + Memanto: Persistent Agent Memory

> **Give your CrewAI agents long-term memory that persists across sessions and shares across agents.**

This integration replaces CrewAI's default ephemeral memory with [Memanto](https://github.com/moorcheh-ai/memanto) — a typed semantic memory system with zero-ingestion-latency exact search.

## Why Memanto for CrewAI?

| Feature | Default CrewAI Memory | CrewAI + Memanto |
|---------|----------------------|------------------|
| Persistence | In-memory (lost on exit) | **Permanent** (survives restarts) |
| Cross-session | ❌ | ✅ Agents recall from past runs |
| Cross-agent | Limited | ✅ Any agent reads any agent's memories |
| Search quality | Approximate (vector DB) | **Exact** (information-theoretic) |
| Ingestion delay | Seconds (indexing) | **Zero** (instant searchability) |
| Memory types | Flat | **13 typed categories** (fact, decision, preference, ...) |

## Quick Start

### 1. Install

```bash
pip install crewai memanto
```

### 2. Get API Keys

- **Moorcheh API Key** (for Memanto): [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys) — free tier includes 100K operations/month
- **OpenAI API Key** (for CrewAI's LLM): [platform.openai.com](https://platform.openai.com)

### 3. Set Environment

```bash
export MOORCHEH_API_KEY="your-moorcheh-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

### 4. Run the Demo

```bash
# Full pipeline: Research Agent stores → Writer Agent recalls
python main.py

# Prove cross-session persistence (run AFTER the first run)
python main.py --recall-only

# Custom topic
python main.py --topic "quantum computing breakthroughs in 2026"
```

## How to Swap Standard CrewAI Memory for Memanto

The swap is **3 lines of code**:

```python
from crewai.memory.unified_memory import Memory
from memanto_backend import MemantoStorageBackend

# Before (default CrewAI memory — ephemeral):
# crew = Crew(agents=[...], tasks=[...], memory=True)

# After (Memanto-backed — persistent, cross-session, cross-agent):
backend = MemantoStorageBackend(api_key="your-key", namespace="my-project")
memory = Memory(storage=backend)
crew = Crew(agents=[...], tasks=[...], memory=memory)
```

That's it. Your agents now have permanent memory.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CrewAI Crew                          │
│                                                         │
│  ┌─────────────┐              ┌─────────────┐          │
│  │  Research    │   memory     │   Writer    │          │
│  │   Agent     │──remember──▶ │   Agent     │          │
│  └─────────────┘              └──────┬──────┘          │
│                                      │ recall          │
│  ┌───────────────────────────────────┼──────────────┐  │
│  │           CrewAI Memory           │              │  │
│  │     (Memory class instance)       ▼              │  │
│  └───────────────────────────────────┼──────────────┘  │
│                                      │                  │
└──────────────────────────────────────┼──────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │    MemantoStorageBackend            │
                    │    (implements StorageBackend)       │
                    └──────────────────┼──────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │          Moorcheh Cloud              │
                    │   (exact semantic search engine)     │
                    │   • Zero ingestion latency           │
                    │   • Typed memory categories          │
                    │   • 100K free ops/month              │
                    └─────────────────────────────────────┘
```

## Demo Scenario

The demo shows a two-agent crew where memories flow from Research → Writer:

1. **Research Agent** investigates a topic and stores findings
2. **Writer Agent** recalls those findings from Memanto and writes a summary
3. **Cross-session test**: Run again with `--recall-only` — the Writer Agent still has access to the Research Agent's findings from the previous session

This proves both inter-agent and cross-session memory persistence.

## Advanced Usage

### Scoped Memory (Team/Project Isolation)

```python
# Each project gets its own namespace — complete isolation
backend_project_a = MemantoStorageBackend(namespace="project-alpha")
backend_project_b = MemantoStorageBackend(namespace="project-beta")
```

### Memory Categories

Memanto supports 13 typed categories for cleaner retrieval:

```python
memory.remember(
    content="User prefers bullet-point summaries over prose",
    categories=["preference"],  # typed for better recall
    scope="/users/anthony",
    importance=0.9,
)

# Later — recall only preferences
results = memory.recall(
    query="how does the user like output formatted?",
    categories=["preference"],
)
```

### Handling Contradictory Memories

Memanto naturally handles contradictions via importance scoring and recency:

```python
# Old memory
memory.remember(
    content="Project deadline is March 15",
    categories=["fact"],
    importance=0.7,
)

# Updated memory (higher importance + more recent = wins in recall)
memory.remember(
    content="Project deadline moved to April 1 per stakeholder meeting",
    categories=["fact", "decision"],
    importance=0.95,
)
```

## File Structure

```
examples/crewai-integration/
├── README.md              # This file
├── requirements.txt       # Dependencies
├── memanto_backend.py     # StorageBackend implementation (the integration)
└── main.py                # Demo: Research Agent → Writer Agent
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `MOORCHEH_API_KEY not set` | Get key at [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys) |
| `Namespace not found` | Backend auto-creates on first write — just run the demo |
| `recall returns empty` | Run without `--recall-only` first to populate memory |
| `Rate limit` | Free tier allows 100K ops/month — more than enough for dev |

## License

MIT — same as Memanto.
