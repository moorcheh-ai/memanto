# 🐜 CrewAI + Memanto: Best-in-Class Agent Memory Integration

> **Bounty submission for [moorcheh-ai/memanto#37](https://github.com/moorcheh-ai/memanto/issues/37)**

A production-ready example showing how to replace CrewAI's default short-lived memory with **Memanto** — providing permanent, semantic, cross-session agent memory.

## 🎯 The Problem

CrewAI agents are powerful but suffer from **"long-term amnesia"** — they forget everything between sessions. The default memory is ephemeral and siloed per agent.

## ✅ Our Solution

This demo shows how to:
1. **Replace standard CrewAI memory with Memanto** as the primary memory layer
2. **Share knowledge across agents** — Research Agent's findings are immediately available to Writer Agent
3. **Persist across sessions** — memories survive agent restarts
4. **Use typed memory** — facts, preferences, learnings, observations, decisions are categorized for better retrieval
5. **Detect contradictions** — Memanto spots when new info conflicts with old

## 🏗️ Architecture

```
┌─────────────────┐     store     ┌──────────────────┐
│  Research Agent  │──────────────▶│                  │
│  (CrewAI)        │               │    Memanto        │
└─────────────────┘               │  (Semantic DB)    │
                                   │                  │
┌─────────────────┐     recall    │  - Instant search  │
│  Writer Agent    │◀─────────────│  - Typed memory    │
│  (CrewAI)        │               │  - Contradiction   │
└─────────────────┘               │    detection       │
                                   └──────────────────┘
```

## 📋 What This Demo Does

### Phase 1: Research Agent stores findings
- Stores 6 facts/preferences/learnings into Memanto
- Each with appropriate memory type classification

### Phase 2: Session ends
- Simulates time passing (next day scenario)

### Phase 3: Writer Agent retrieves
- Searches Memanto for previous research
- Retrieves context-aware results

### Phase 4: Grounded RAG answers
- Writer Agent asks Memanto questions
- Gets answers backed by stored memories

### Phase 5: Contradiction detection (Bonus!)
- Stores a conflicting memory
- Memanto detects and reports the contradiction

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.10+ required
python --version  # Should be >= 3.10

# Install Memanto
pip install memanto

# Install CrewAI (optional — demo works standalone too)
pip install crewai
```

### Setup

```bash
# 1. Get your free Moorcheh API key
#    Visit: https://console.moorcheh.ai/api-keys

# 2. Configure Memanto (one-time)
memanto
#    Enter your API key when prompted

# 3. Create the agent namespace
memanto agent create memeory-demo
memanto agent activate memeory-demo
```

### Run the Demo

```bash
# With CrewAI (full demo):
python crewai_memanto_demo.py

# Standalone (no CrewAI needed):
python crewai_memanto_demo.py  # Auto-detects and falls back
```

## 📖 How to Swap Standard CrewAI Memory for Memanto

### Before (standard CrewAI memory — forgets everything):

```python
from crewai import Agent, Crew

agent = Agent(
    role="Researcher",
    goal="Research topics",
    memory=True,  # Default: ephemeral, siloed
)
```

### After (Memanto — persistent, cross-agent):

```python
from crewai import Agent
from memanto_client import MemantoClient, MemantoStoreTool, MemantoRecallTool

mc = MemantoClient("my-agent")

agent = Agent(
    role="Researcher",
    goal="Research topics",
    tools=[
        MemantoStoreTool(mc),   # Store findings permanently
        MemantoRecallTool(mc),  # Search past findings
    ],
    # No default memory=True — Memanto handles it all
)
```

### Key Differences

| Feature | CrewAI Default | With Memanto |
|---------|---------------|-------------|
| Persistence | Per-session only | Permanent |
| Cross-agent | No | Yes — shared namespace |
| Search | Basic keyword | Semantic + typed |
| Contradiction detection | None | Built-in |
| Export | Manual | One command |
| Storage cost at idle | Always running | Zero (serverless) |

## 🧠 Memory Types Used

| Type | Use Case | Example |
|------|----------|---------|
| `fact` | Objective information | "67% growth in AI agent adoption Q1 2026" |
| `preference` | User choices | "User prefers dark mode" |
| `learning` | Insights gained | "Memanto reduces context-loss by 40%" |
| `observation` | Noted patterns | "Users frustrated by context loss" |
| `decision` | Actions taken | "Set default theme to dark mode" |
| `event` | Occurrences | "User logged in from Shanghai" |
| `context` | Situational info | "Current project phase is testing" |

## 🎬 Visual Proof

> **Recording**: See `demo-recording.gif` (or [Loom link here])
>
> The recording shows:
> 1. Research agent storing 6 memories with different types
> 2. Session ending
> 3. Writer agent successfully recalling all 6 memories
> 4. RAG answer confirming memory retrieval
> 5. Contradiction detection in action

## 📁 Files

```
memanto-crewai/
├── crewai_memanto_demo.py   # Main demo script
├── README.md                 # This file
└── demo-recording.gif        # Visual proof
```

## 🔗 Links

- [Memanto GitHub](https://github.com/moorcheh-ai/memanto)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
- [Bounty Issue #37](https://github.com/moorcheh-ai/memanto/issues/37)
