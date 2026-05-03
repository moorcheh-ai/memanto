# CrewAI + Memanto Agentic Memory Integration

> 🏆 Bounty Submission for [Issue #37: Best-in-Class Integration: CrewAI + Memanto](https://github.com/moorcheh-ai/memanto/issues/37)

## What This Does

This integration replaces CrewAI's built-in **short-term session memory** with Memanto's **persistent, cross-session semantic memory**. Agents can now:

- 🔁 **Remember across sessions** — findings from one run are available in the next
- 🤝 **Share knowledge between agents** — Research Agent findings are accessible to Writer Agent
- 🔄 **Handle contradictions** — old facts can be updated with new information while maintaining provenance
- 🎯 **Semantic search** — agents find relevant memories using natural language queries

## Quick Start

### 1. Install

```bash
pip install crewai memanto
```

### 2. Get API Key

Visit [Moorcheh Console](https://console.moorcheh.ai/api-keys) to create your API key.

```bash
export MOORCHEH_API_KEY="your_api_key"
```

### 3. Run Demo

```bash
python crewai_memanto_integration.py
```

## The "Memory Test" Use Case

The demo implements the exact scenario from the bounty requirements:

1. **Research Agent** studies Python history and stores 4 facts + 1 preference in Memanto
2. **Writer Agent** retrieves those findings using semantic search (different logical session)
3. **Contradiction handling** — Writer updates a memory with more specific information
4. **Cross-agent sharing** — memories are scoped per-agent but retrievable by others

### Output Example

```
============================================================
CrewAI + Memanto: Cross-Session Memory Demo
============================================================

📋 Phase 1: Research Agent working...
----------------------------------------
  ✓ Stored: Python was created by Guido van Rossum in 1991... (ID: abc12345)
  ✓ Stored: Python's design philosophy emphasizes code read... (ID: def67890)
  ✓ Stored: Python supports multiple programming paradigms... (ID: ghi11111)
  ✓ Stored: The Python Package Index (PyPI) hosts over 40... (ID: jkl22222)
  ✓ Stored preference (ID: mno33333)

📝 Phase 2: Writer Agent retrieving memories...
----------------------------------------
  Retrieved 4 memories:
    [fact] Python was created by Guido van Rossum in 1991... (relevance: 0.92)
    [fact] Python supports multiple programming paradigms... (relevance: 0.88)
    [fact] Python's design philosophy emphasizes code read... (relevance: 0.85)
    [fact] The Python Package Index (PyPI) hosts over 400... (relevance: 0.81)

  Retrieved 1 preferences:
    [preference] User prefers concise answers with bullet points...

🔄 Phase 3: Handling contradictory memories...
----------------------------------------
  ✓ Updated memory: contradiction handled
    Old: Python was created by Guido van Rossum in 1991...
    New: Python was created by Guido van Rossum and first released in February 1991

============================================================
Demo complete! Memories persist across sessions via Memanto.
============================================================
```

## Architecture

```
┌─────────────────────────────────────────────┐
│              CrewAI Crew                     │
│  ┌──────────────┐      ┌──────────────┐     │
│  │  Researcher  │─────▶│    Writer    │     │
│  │   Agent      │      │    Agent     │     │
│  └──────┬───────┘      └──────┬───────┘     │
│         │                     │             │
│         ▼                     ▼             │
│  ┌───────────────────────────────────┐     │
│  │    Memanto Memory Adapter         │     │
│  │  (store / recall / update / share)│     │
│  └──────────────┬────────────────────┘     │
└─────────────────┼─────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │   Memanto API  │
         │ (Moorcheh SDK) │
         │  Persistent    │
         │  Semantic DB   │
         └────────────────┘
```

## How to Swap CrewAI Memory for Memanto

### Before (Standard CrewAI)

```python
from crewai import Agent

agent = Agent(
    role="Researcher",
    goal="Find information",
    backstory="You research topics.",
)
# Memory is session-only — lost between runs
```

### After (With Memanto)

```python
from crewai_memanto_integration import MemantoAgent

agent = MemantoAgent(
    name="Researcher",
    role="Researcher", 
    goal="Find information",
    backstory="You research topics and store findings in Memanto.",
)

# Store — persists across sessions
await agent.store_memory("Key finding", memory_type="fact")

# Recall — from any session
memories = await agent.recall_memories("search query")
```

## Memory Types

| Type | Use Case | Example |
|------|----------|---------|
| `fact` | Research findings | "Python was created in 1991" |
| `preference` | User preferences | "User prefers concise answers" |
| `decision` | Workflow decisions | "Chose SQLite over PostgreSQL" |
| `instruction` | Agent rules | "Always cite sources" |
| `context` | Contextual info | "Project deadline: 2026-06-01" |
| `event` | Notable events | "Deployment completed" |
| `observation` | Agent observations | "API response time degraded" |
| `error` | Errors encountered | "Connection timeout on retry 3" |

## Cross-Agent Memory Sharing

```python
# Agent A shares a finding with Agent B
await agent_a.share_memory(
    "Critical API endpoint changed to /v2/users",
    target_agent_id="agent-b"
)

# Agent B retrieves shared findings
shared = await agent_b.receive_shared_memories(
    source_agent_id="agent-a",
    query="API endpoint changes"
)
```

## Contradiction Handling

Memanto tracks memory provenance. When updating a memory:

```python
# Old fact stored
old_id = await agent.store_memory("Temperature is 25°C")

# New measurement contradicts old one
new_id = await agent.memory.update(
    old_id,
    "Temperature is now 28°C",
    reason="sensor reading updated"
)
# Old memory is marked as superseded, not deleted
# Both records preserved for audit trail
```

## Files

| File | Description |
|------|-------------|
| `crewai_memanto_integration.py` | Main integration code + demo |
| `README.md` | This file |

## Requirements

- Python 3.10+
- `crewai` >= 0.30
- `memanto` >= 0.1
- `moorcheh-sdk` >= 0.1 (installed with memanto)

## License

MIT
