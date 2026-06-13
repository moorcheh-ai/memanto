# Memanto + mattpocock Skills: Persistent Context Bridge

Bridges the **Context Fragmentation** gap between mattpocock's developer skills ecosystem by using Memanto as a shared persistent memory layer.

## Problem
Skills like `/grill-with-docs`, `/tdd`, and `/handoff` run in isolated sessions — context from one is invisible to another.

## Solution
Memanto acts as a "permanent brain" that stores and retrieves context across all skill invocations.

## How It Works

```
Skill A (grill-with-docs) --> Memanto (stores architecture context)
Skill B (tdd)              <-- Memanto (recalls architecture context)
Skill C (handoff)          <-- Memanto (recalls ALL prior context)
```

## Usage

```python
from memanto_client import MemantoMemory
memory = MemantoMemory()

# In Skill A: "We chose FastAPI for the backend"
memory.store("project-alpha", "tech_stack", "FastAPI + React")

# In Skill B (later session):
context = memory.recall("project-alpha")
print(context["tech_stack"])  # "FastAPI + React"
```

## Demo
Run `python examples/memanto-skills/demo.py` to see context flow between simulated skills.
