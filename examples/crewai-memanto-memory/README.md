# CrewAI + Memanto Agentic Memory — Research-to-Writer Pipeline

Demonstrates Memanto as CrewAI's primary memory layer, solving the "long-term amnesia" problem where agents lose context across sessions.

## What This Demo Shows

1. **Research Agent** investigates a topic and stores findings in Memanto
2. **Writer Agent** (run separately — simulating a 24hr gap) retrieves past research from Memanto and produces a report
3. Memory survives across independent Python invocations via Memanto's persistent backend

## Quick Start

```bash
pip install crewai memanto

# Phase 1: Research Agent gathers + stores in Memanto
python memory_research_crew.py --topic "AI agent memory systems in 2026" --phase research

# Simulate a day passing... then:

# Phase 2: Writer Agent retrieves from Memanto and writes report
python memory_research_crew.py --topic "AI agent memory systems in 2026" --phase write
```

## How to Swap Standard CrewAI Memory for Memanto

Standard CrewAI uses in-memory context that evaporates when the process ends. Here's the swap:

### Before (standard CrewAI memory)
```python
agent = Agent(
    role="Researcher",
    goal="Research topics",
    backstory="You are a researcher",
    memory=True,  # Default: ephemeral, lost on exit
)
```

### After (Memanto-backed memory)
```python
from memanto import MemantoClient

memanto = MemantoClient()

# Store findings (survives process death)
memanto.remember(
    text="Key finding: 78% of agents lose context across sessions",
    metadata={"agent": "researcher", "confidence": 0.9}
)

# Retrieve later (different process, different day)
results = memanto.recall(query="agent context loss", limit=5)

# Inject into agent's context
context = "\n".join(r.text for r in results)
agent = Agent(
    role="Writer",
    goal="Write reports",
    backstory=f"Prior research:\n{context}",  # Survived the gap!
)
```

## Memory Persistence

The `CrewAIMemantoMemory` adapter class in this example wraps Memanto's SDK and provides:
- `remember(content, metadata)` — store with provenance
- `recall(query, limit)` — semantic search across all past memories
- `get_context()` — injectable context string for agent backstories

Run `--phase research`, close the terminal, come back tomorrow, run `--phase write` — the Writer Agent picks up exactly where the Research Agent left off.

## Requirements

- Python 3.10+
- `crewai>=1.14.0`
- `memanto>=0.0.8`
- OpenAI API key (or any LiteLLM-compatible backend via `CREWAI_MODEL` and `CREWAI_BASE_URL` env vars)
