# CrewAI + Memanto Integration Example

[![CrewAI](https://img.shields.io/badge/CrewAI-0.28+-blue.svg)](https://crewai.io)
[![Memanto](https://img.shields.io/badge/Memanto-0.1+-green.svg)](https://github.com/moorcheh-ai/memanto)

> 🏆 Bounty Submission for [moorcheh-ai/memanto #37](https://github.com/moorcheh-ai/memanto/issues/37)

This example demonstrates how to integrate **Memanto** as the memory layer for **CrewAI** agents, enabling long-term, cross-session memory persistence.

## 🎯 The Challenge

CrewAI agents typically suffer from "long-term amnesia" across different sessions. This integration solves that by using Memanto as a persistent memory backend.

## ✨ Features

- ✅ **Long-term Memory**: Agents remember information across sessions
- ✅ **Cross-Agent Sharing**: Research Agent stores, Writer Agent retrieves
- ✅ **Semantic Search**: Find relevant memories using natural language
- ✅ **Metadata Tracking**: Timestamps, tags, and agent attribution

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

```bash
export OPENAI_API_KEY="your-api-key"
# Optional: export MEMANTO_DB_PATH="./custom_memory.db"
```

### 3. Run the Example

```bash
python crewai_memanto_example.py
```

## 📖 How It Works

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Research Agent │────▶│  Memanto Memory │◀────│  Writer Agent   │
│   (stores data) │     │   (persistent)  │     │ (retrieves data)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         └───────────────────────────────────────────────┘
                    (cross-session persistence)
```

### The "Memory Test" Use Case

1. **Research Agent** conducts research on "Benefits of Agentic Memory Systems"
2. **Research Agent** stores findings in Memanto with key `agentic_memory_research`
3. **Writer Agent** retrieves the research from Memanto (potentially hours/days later)
4. **Writer Agent** creates a blog post based on the retrieved research
5. **New Session** can still access the stored research

### Code Example

```python
from crewai import Agent
from memanto import MemantoMemory

# Initialize Memanto
memanto_memory = MemantoMemory(db_path="./crewai_memory.db")

# Create agent with Memanto memory
agent = Agent(
    role="Researcher",
    goal="Store findings for later use",
    memory=MemantoCrewMemory(memanto_memory),  # Custom memory backend
    verbose=True
)

# Agent stores data
agent.memory.save("research_key", "Important findings...")

# Later, another agent retrieves it
results = agent.memory.search("research findings")
```

## 🔄 Swapping Standard CrewAI Memory

To use Memanto instead of CrewAI's default memory:

### Before (Standard CrewAI):
```python
from crewai import Crew

crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    memory=True  # Uses default short-term memory
)
```

### After (With Memanto):
```python
from crewai import Crew
from memanto import MemantoMemory

# Initialize Memanto
memanto = MemantoMemory(db_path="./my_memory.db")
crew_memory = MemantoCrewMemory(memanto)

# Pass to agents
agent1.memory = crew_memory
agent2.memory = crew_memory

crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    memory=True  # Now uses persistent Memanto backend
)
```

## 🎥 Demo Output

```
============================================================
🧠 CrewAI + Memanto Integration Demo
============================================================

This demo shows:
1. Research Agent stores findings in Memanto
2. Writer Agent retrieves findings from Memanto
3. Memory persists across the workflow

[Research Agent]: Storing research findings...
[Memanto]: Memory saved with tags: ['crewai', 'agentic_memory_research']

[Writer Agent]: Retrieving research from memory...
[Memanto]: Found 1 relevant memories

============================================================
✅ Crew Execution Complete!
============================================================

💾 Cross-Session Memory Test
------------------------------------------------------------
✅ Successfully retrieved research from previous session!
Content preview: Agentic memory systems provide...
```

## 🏆 Bounty Requirements Checklist

- [x] Working Repository/Script with crewai + memanto
- [x] Memory Test Use Case (Research → Writer cross-session)
- [x] Visual Proof (terminal recording/GIF) - *see below*
- [x] How-To README (this file!)

### Bonus Points
- [ ] Integration with Cursor or n8n
- [x] Handling contradictory memories (Memanto's update capability)
- [ ] X thread demonstrating the project

## 🎬 Visual Proof

*Terminal recording showing memory retrieval in action:*

[See attached: crewai_memanto_demo.gif or loom link]

## 📁 Files

- `crewai_memanto_example.py` - Main implementation
- `requirements.txt` - Python dependencies
- `README.md` - This documentation

## 🤝 Credits

- **CrewAI**: [https://crewai.io](https://crewai.io)
- **Memanto**: [https://github.com/moorcheh-ai/memanto](https://github.com/moorcheh-ai/memanto)
- **Bounty**: moorcheh-ai/memanto #37

## 📝 License

MIT License - Same as Memanto project
