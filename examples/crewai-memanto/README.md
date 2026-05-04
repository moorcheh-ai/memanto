# 🐜 CrewAI + Memanto — Persistent Cross-Session Memory

A best-in-class integration giving CrewAI agents **permanent, searchable, cross-session memory** via [Memanto](https://github.com/moorcheh-ai/memanto).

```
Session A (any time):   ResearchAgent  →  stores findings  →  Memanto
Session B (days later): WriterAgent    ←  recalls findings  ←  Memanto
```

No more "long-term amnesia." Every finding, preference, and decision survives across Python processes, container restarts, and days-long gaps between runs.

---

## Why Memanto?

| Problem with standard CrewAI memory | How Memanto solves it |
|--------------------------------------|----------------------|
| Resets between Python runs | Memories persist forever in Moorcheh's semantic DB |
| One agent can't read another's session | All agents share one `agent_id` namespace |
| No semantic search | Exact semantic retrieval — no indexing delay |
| No conflict resolution | `correct_memory` preserves old fact in audit trail |
| Heavy vector DB setup | One `pip install memanto` + one API key |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/YOUR_HANDLE/memanto
cd memanto/examples/crewai-memanto
pip install -r requirements.txt
```

### 2. Configure

```bash
# Get your free key at https://moorcheh.ai
export MOORCHEH_API_KEY=mk-...

# Your LLM key (CrewAI default uses OpenAI)
export OPENAI_API_KEY=sk-...

# Start the Memanto local server
memanto serve
```

### 3. Run the demo (no LLM needed)

```bash
# Proves store → recall → correct → recall cycle
python examples/memory_demo.py
```

### 4. Run the full crew

```bash
# Session A: ResearchAgent stores findings
python run.py --topic "AI coding assistants in 2025" --mode research

# Session B: WriterAgent recalls them (separate process, simulates days later)
python run.py --topic "AI coding assistants in 2025" --mode write

# Or run both in sequence
python run.py --topic "AI coding assistants in 2025" --mode full
```

---

## How to Swap CrewAI's Default Memory for Memanto

CrewAI's built-in memory uses SQLite + ChromaDB locally. Replacing it with Memanto takes **3 lines**:

### Before (standard CrewAI)

```python
from crewai import Crew

crew = Crew(
    agents=[research_agent, writer_agent],
    tasks=[research_task, write_task],
    memory=True,  # uses local SQLite/ChromaDB
)
```

### After (Memanto-backed)

```python
from crewai import Crew
from memanto_bridge import MeMantoCrewMemory          # ← add

mem = MeMantoCrewMemory(agent_id="my-crew")           # ← add

crew = Crew(
    agents=[research_agent, writer_agent],
    tasks=[research_task, write_task],
    memory=True,
    memory_config={                                    # ← add
        "provider": "custom",
        "config": {"memory": mem},
    },
)
```

That's it. All `save()` and `search()` calls CrewAI makes internally now go through Memanto.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Your CrewAI Crew                    │
│                                                     │
│  ┌──────────────────┐    ┌──────────────────────┐  │
│  │  ResearchAgent   │    │    WriterAgent        │  │
│  │                  │    │                      │  │
│  │  store_finding() │    │  recall_memory()     │  │
│  │  recall_memory() │    │  answer_from_memory()│  │
│  │  correct_memory()│    │                      │  │
│  └────────┬─────────┘    └──────────┬───────────┘  │
│           │                         │              │
│           └──────────┬──────────────┘              │
│                      │                             │
│          ┌───────────▼───────────┐                 │
│          │  MeMantoCrewMemory    │                 │
│          │  (memanto_bridge)     │                 │
│          └───────────┬───────────┘                 │
└──────────────────────┼─────────────────────────────┘
                       │ REST API (v2)
           ┌───────────▼───────────┐
           │   Memanto Server      │
           │  (memanto serve)      │
           └───────────┬───────────┘
                       │ SDK calls
           ┌───────────▼───────────┐
           │    Moorcheh.ai        │
           │  Zero-Index Semantic  │
           │  Database + RAG       │
           └───────────────────────┘
```

---

## Memory Types Used

Memanto supports 13 typed semantic memory categories. This integration uses:

| Type | Used for |
|------|----------|
| `fact` | Research findings stored by ResearchAgent |
| `preference` | User style/tone preferences |
| `decision` | Key editorial decisions |
| `observation` | General agent notes |

Store with a specific type for cleaner retrieval:

```python
mem.store_finding(content="GPT-4o costs $5/1M input tokens", agent="ResearchAgent", tags=["pricing"])
mem.store_preference(content="User prefers bullet-point summaries", agent="WriterAgent")
```

---

## Handling Contradictory Memories (Bonus Feature)

When new research contradicts an old finding, `correct_memory` updates the active fact while **archiving the old content** in audit metadata:

```python
# ResearchAgent stored this in Session A:
# id="mem_abc123", content="GitHub Copilot has 1.8M users"

# Session B: new data found
mem.correct_memory(
    memory_id="mem_abc123",
    new_fact="GitHub Copilot surpassed 2.3M developers as of Q2 2025"
)

# What Memanto now stores:
# content  = "GitHub Copilot surpassed 2.3M developers as of Q2 2025"
# metadata.previous_content = "GitHub Copilot has 1.8M users"   ← audit trail
# metadata.correction = True
# metadata.updated_at = 1748000000.0
```

The old fact is never lost — it's always recoverable from metadata.

---

## Project Structure

```
crewai-memanto/
├── memanto_bridge/
│   ├── __init__.py           # Public exports
│   ├── memory.py             # Low-level Memanto v2 REST client
│   └── crew_memory.py        # CrewAI-compatible memory backend
├── crew/
│   ├── __init__.py
│   ├── crew.py               # Crew + Agent + Task definitions
│   └── tools.py              # CrewAI BaseTool wrappers for Memanto ops
├── examples/
│   └── memory_demo.py        # Standalone demo (no LLM key needed)
├── run.py                    # CLI entry point
├── requirements.txt
└── README.md
```

---

## Memanto REST API Reference (v2)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2/agents` | POST | Create agent namespace |
| `/api/v2/agents/{id}/activate` | POST | Start session → get token |
| `/api/v2/agents/{id}/remember` | POST | Store one memory |
| `/api/v2/agents/{id}/batch-remember` | POST | Store up to 100 memories |
| `/api/v2/agents/{id}/recall` | GET | Semantic search |
| `/api/v2/agents/{id}/answer` | POST | RAG answer over memories |
| `/api/v2/agents/{id}/memories/{mem_id}` | PATCH | Correct/update a memory |

All endpoints require:
```
Authorization: Bearer {moorcheh_api_key}
X-Session-Token: {session_token}   # from /activate
```

---

## Cursor Integration (Bonus)

Add to your Cursor `mcp_config.json`:

```json
{
  "mcpServers": {
    "memanto": {
      "command": "memanto",
      "args": ["connect", "cursor"],
      "env": {
        "MOORCHEH_API_KEY": "mk-YOUR_KEY_HERE"
      }
    }
  }
}
```

Then run:
```bash
memanto connect cursor
```

Your Cursor agent now shares the same memory namespace as your CrewAI crews.

---

## Citation

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
  title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
  author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
  year={2026},
  eprint={2604.22085},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2604.22085},
}
```
