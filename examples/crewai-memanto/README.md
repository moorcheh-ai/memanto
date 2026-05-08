# CrewAI + Memanto: Agentic Memory Integration

> Best-in-Class Integration: CrewAI agents with Memanto's persistent, searchable, context-aware memory.

## The Problem

CrewAI agents are powerful, but they suffer from **"long-term amnesia"** — they can't recall information across different sessions or share context with other agents that run later.

## The Solution

**Memanto** provides a permanent, searchable, and context-aware memory layer for AI agents. By integrating Memanto with CrewAI, agents can:

- ✅ Store findings that persist across sessions
- ✅ Recall information from previous runs
- ✅ Share context between different agents in a Crew
- ✅ Handle contradictory memories (supersede outdated facts)
- ✅ Trust-score memories based on provenance and validation

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   CrewAI Crew                        │
│                                                      │
│  ┌──────────────┐         ┌──────────────┐          │
│  │ Research      │  Store  │ Writer       │  Recall  │
│  │ Agent         │────────▶│ Agent        │◀────────│
│  │              │         │              │          │
│  └──────┬───────┘         └──────┬───────┘          │
│         │                        │                   │
│         ▼                        ▼                   │
│  ┌─────────────────────────────────────────────┐    │
│  │          Memanto Memory Layer                │    │
│  │  ┌─────────────┐  ┌────────────────────┐    │    │
│  │  │ Long-Term   │  │ Short-Term (TTL)   │    │    │
│  │  │ Memory      │  │ Memory             │    │    │
│  │  └──────┬──────┘  └──────────┬─────────┘    │    │
│  │         ▼                     ▼              │    │
│  │  ┌─────────────────────────────────────┐     │    │
│  │  │       Moorcheh Semantic Search       │     │    │
│  │  │   (persistent, searchable, scoped)   │     │    │
│  │  └─────────────────────────────────────┘     │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
pip install crewai memanto moorcheh-sdk
```

### 2. Set Your API Key

```bash
export MOORCHEH_API_KEY="your-moorcheh-api-key"
```

### 3. Run the Demo

```bash
python examples/crewai-memanto/crewai_memanto_integration.py
```

## How-To: Swap Standard CrewAI Memory for Memanto

### Before (Standard CrewAI Memory)

```python
from crewai import Crew

crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,  # Uses default ephemeral memory
)
```

### After (Memanto-Powered Memory)

```python
from crewai import Crew
from examples.crewai_memanto.crewai_memanto_integration import (
    MemantoLongTermMemory,
    MemantoShortTermMemory,
)

SCOPE_ID = "my-crew"  # Shared scope for all agents in the crew

crew = Crew(
    agents=[...],
    tasks=[...],
    memory=True,
    long_term_memory=MemantoLongTermMemory(scope_id=SCOPE_ID),
    short_term_memory=MemantoShortTermMemory(scope_id=SCOPE_ID),
)
```

**That's it!** Your agents now have persistent, searchable memory that survives across sessions.

### Using the Simplified Helper API

For direct memory control without CrewAI's abstraction:

```python
from examples.crewai_memanto.crewai_memanto_integration import MemantoMemoryHelper

helper = MemantoMemoryHelper(scope_id="research-crew")

# Store a finding
helper.remember(
    "Quantum computing uses qubits that can exist in superposition",
    memory_type="fact",
    tags=["quantum", "computing"],
)

# Recall findings (even in a different session!)
results = helper.recall("quantum computing")

# Handle contradictory memories
helper.supersede(
    old_content="GPT-4 is the best LLM",
    new_content="Claude 3.5 Sonnet is the best LLM for coding tasks",
)
```

## The "Memory Test" Use Case

This integration demonstrates a scenario where:

1. **Session 1**: A Research Agent investigates "AI safety" and stores key findings in Memanto
2. **Session 2**: A Writer Agent retrieves those findings — even hours or days later — and writes a summary

The Writer Agent doesn't need to be in the same process or even the same machine. It just needs access to the same Memanto scope.

### Expected Output

```
📝 Session 1: Research Agent stores findings...
  ✅ Stored: AI Alignment Overview
     ID: abc123...
  ✅ Stored: Scalable Oversight Challenge
     ID: def456...
  ✅ Stored: Alignment Tax Concept
     ID: ghi789...

🔍 Session 2: Writer Agent retrieves findings...
  Found 3 memories:
  
  1. AI Alignment Overview
     Type: fact
     Confidence: 0.8
     Content: AI alignment research focuses on ensuring AI systems pursue intended goals...
  
  2. Scalable Oversight Challenge
     Type: fact
     Confidence: 0.8
     Content: Scalable oversight is a key challenge: as AI systems become more capable...
  
  3. Alignment Tax Concept
     Type: fact
     Confidence: 0.8
     Content: The alignment tax refers to the cost of making AI systems safe...
```

## Key Features

### 1. Persistent Long-Term Memory
Memories survive across sessions. A Research Agent's findings from Monday are available to a Writer Agent on Friday.

### 2. TTL-Based Short-Term Memory
Short-term memories auto-expire after a configurable TTL (default: 1 hour). Perfect for temporary context that shouldn't pollute long-term storage.

### 3. Contradiction Handling
When an old fact is superseded by new information, Memanto marks the old memory as superseded and stores the new one with provenance tracking:

```python
helper.supersede(
    old_content="outdated fact",
    new_content="updated fact",
)
```

### 4. Scoped Memory Isolation
Each Crew or project can have its own memory scope, preventing cross-contamination:

```python
# Research crew has its own memory
research_helper = MemantoMemoryHelper(scope_id="research-crew")

# Marketing crew has separate memory
marketing_helper = MemantoMemoryHelper(scope_id="marketing-crew")
```

### 5. Trust Scores
Every memory has a computed confidence score based on:
- Provenance (explicit > validated > inferred)
- Validation count (more validations = higher confidence)
- Age decay (fresher preferences are more trustworthy)
- Contradiction detection (contradicted = low confidence)

## Files

| File | Description |
|------|-------------|
| `crewai_memanto_integration.py` | Full integration code with all classes and demo |
| `README.md` | This file |

## Requirements

- Python 3.10+
- crewai
- memanto
- moorcheh-sdk
- A Moorcheh API key ([get one here](https://moorcheh.ai))

## License

MIT
