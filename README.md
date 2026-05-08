# Memanto ↔ CrewAI Integration

[![PyPI](https://img.shields.io/pypi/v/memanto)](https://pypi.org/project/memanto/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Persistent, typed, semantic memory for CrewAI agents — powered by Memanto.**

This integration lets your CrewAI agents leverage Memanto's state-of-the-art memory engine: zero-ingestion-latency semantic search, 13 typed memory categories, temporal queries, provenance tracking, and built-in RAG — all through a simple CrewAI-compatible interface.

## 📦 Installation

```bash
pip install memanto crewai
```

You'll also need a **Moorcheh API key**. Get one free at [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys).

```bash
export MOORCHEH_API_KEY=moorch_your_key_here
```

## 🚀 Quick Start

### Option 1: Plug into a CrewAI Agent

```python
import os
from crewai import Agent, Task, Crew
from memanto.crewai_memanto import MemantoCrewMemory

# Create Memanto-backed memory
memory = MemantoCrewMemory(
    api_key=os.environ["MOORCHEH_API_KEY"],
    agent_id="research-agent",
)

# Create a CrewAI agent with persistent memory
researcher = Agent(
    role="Senior Researcher",
    goal="Uncover and remember groundbreaking insights",
    backstory="An expert analyst with perfect memory.",
    memory=memory,
    verbose=True,
)

task = Task(
    description="Research the latest trends in AI memory systems",
    expected_output="A detailed report",
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[task])
crew.kickoff()

# Later: recall what was learned
results = memory.search("AI memory trends")
for m in results:
    print(f"[{m['type']}] {m['content'][:80]}")
```

### Option 2: Use the Adapter Directly

```python
from memanto.crewai_memanto import MemantoCrewAdapter

adapter = MemantoCrewAdapter(agent_id="my-agent")
adapter.create_agent_if_missing()
adapter.activate()

# Store memories
adapter.remember("fact", "User prefers dark mode", "Dashboard theme should be dark.")
adapter.remember("preference", title="Response style", content="User likes concise answers.")

# Search semantically
results = adapter.recall("What theme does the user want?")
for m in results:
    print(f"  [{m['type']}] {m['content']}")

# RAG-grounded answer
answer = adapter.answer("What should the dashboard theme be?")
print(f"Answer: {answer}")
```

## 🧠 Supported Memory Types

Memanto supports **13 typed memory categories** for clean retrieval and contradiction detection:

| Type | Use Case |
|------|----------|
| `fact` | Objective facts and verified information |
| `preference` | User/agent preferences and stylistic choices |
| `goal` | Active goals and objectives |
| `decision` | Past decisions and their rationale |
| `instruction` | Instructions, guidelines, protocols |
| `commitment` | Promises, deadlines, commitments |
| `event` | Occurrences and timestamped events |
| `relationship` | Relationships between entities |
| `context` | Situational context and environment |
| `observation` | Agent observations and notes |
| `learning` | Knowledge gained, lessons learned |
| `artifact` | References to documents, files, outputs |
| `error` | Errors, failures, and edge cases |

## 🔍 Advanced Queries

### Temporal recall — what was true at a specific time?

```python
memories = adapter.recall_as_of(
    query="user preferences",
    as_of="2026-03-01T00:00:00",
    limit=10,
)
```

### Current-state recall — only non-superseded memories

```python
current = adapter.recall_current(
    query="active goals",
    limit=20,
)
```

### Filter by memory type and tags

```python
preferences = adapter.recall(
    query="communication style",
    memory_types=["preference"],
    tags=["style", "format"],
    min_confidence=0.7,
)
```

## 🛠️ API Reference

### `MemantoCrewMemory`

CrewAI-compatible memory class. Pass to `Agent(memory=...)`.

| Method | Description |
|--------|-------------|
| `save(content, memory_type, title, tags)` | Store a memory (CrewAI convention) |
| `search(query, limit)` | Search stored memories (CrewAI convention) |
| `remember(content, memory_type, ...)` | Alias for `save()` |
| `recall(query, limit)` | Alias for `search()` |
| `answer(question)` | Generate RAG-grounded answer |
| `adapter` | Access the underlying `MemantoCrewAdapter` |

### `MemantoCrewAdapter`

Direct wrapper for use in task callbacks and custom tools.

| Method | Description |
|--------|-------------|
| `create_agent_if_missing()` | Create the Memanto agent if it doesn't exist |
| `activate()` | Start a session |
| `remember(type, title, content, ...)` | Store a memory |
| `recall(query, limit, ...)` | Semantic search |
| `recall_current(query, ...)` | Supersession-aware recall |
| `recall_as_of(query, as_of, ...)` | Point-in-time recall |
| `answer(question)` | RAG-grounded Q&A |
| `list_memories(query, limit)` | List/browse memories |
| `delete_agent()` | Permanently delete agent + all memories |

## ⚠️ Error Handling

All Memanto operations raise standard Python exceptions:

- **`ValueError`** — Invalid input (bad memory type, empty query, etc.)
- **`AgentNotFoundError`** — Referenced agent doesn't exist
- **`SessionError`** — Session not active or expired
- **`SessionExpiredError`** — Session token has expired
- **`ConnectionError`** — Network issues

Example:

```python
from memanto.app.utils.errors import SessionExpiredError

try:
    results = adapter.recall("user preferences")
except SessionExpiredError:
    adapter.activate()
    results = adapter.recall("user preferences")
```

## 🧪 Running the Demo

```bash
export MOORCHEH_API_KEY=moorch_your_key_here
python -m memanto.crewai_memanto
```

Expected output when configured correctly:
```
=== MemantoCrewAdapter Demo ===
Agent 'crewai-demo-agent' ready.
Stored memory: OK
Stored preference: OK

Recall results (2):
  [fact] Memanto now has a CrewAI integration module.
  [preference] The user prefers concise, bullet-point responses.
...
```

## 📄 License

MIT — see the [LICENSE](LICENSE) file.

---

**Built with ❤️ by [Moorcheh.ai](https://moorcheh.ai/)**
