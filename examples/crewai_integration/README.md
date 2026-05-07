# CrewAI + Memanto Integration Example

[![CrewAI](https://img.shields.io/badge/CrewAI-0.28+-blue.svg)](https://crewai.io)
[![Memanto](https://img.shields.io/badge/Memanto-Integration-green.svg)](https://github.com/moorcheh-ai/memanto)

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

### 2. Run the Demo

```bash
python demo_simple.py
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
3. **Writer Agent** retrieves the research from Memanto (24 hours later)
4. **Writer Agent** creates a blog post based on the retrieved research
5. **New Session** can still access the stored research

### Code Example

```python
from memanto import MemantoMemory

# Initialize Memanto
memanto = MemantoMemory(db_path="./crewai_memory.db")

# Create CrewAI agent with Memanto memory
agent = Agent(
    role="Researcher",
    goal="Store findings for later use",
    memory=MemantoCrewMemory(memanto)
)

# Store data
agent.memory.save("research_key", "Important findings...")

# Retrieve later (even in new session)
results = agent.memory.search("research findings")
```

## 🔄 Swapping Standard CrewAI Memory

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
======================================================================
🧠  CrewAI + Memanto Integration Demo
======================================================================

[Memanto] ✓ Initialized with database: crewai_memory.db
🔍  Creating Research Agent...
✍️  Creating Writer Agent...

======================================================================
📚  Task 1: Research Agent conducts research
======================================================================

🔍  Research Agent: Analyzing agentic memory systems...
💾  Storing research to Memanto memory...
[Memanto] ✓ Memory saved with tags: ['crewai', 'agentic_memory_research']

======================================================================
⏰  24 HOURS LATER... New Session Started
======================================================================

✍️  Writer Agent: Starting content creation
🔍  Retrieving research from Memanto...
✓  Found research from previous session!
✓  Content length: 698 characters

📝  Creating blog post...

╔══════════════════════════════════════════════════════════════════╗
║           THE FUTURE OF AI: AGENTIC MEMORY SYSTEMS               ║
╚══════════════════════════════════════════════════════════════════╝

... blog post content ...

💾  Storing blog post to Memanto...
[Memanto] ✓ Memory saved with tags: ['crewai', 'agentic_memory_blog']

======================================================================
🔍  Semantic Search Demo
======================================================================

Query: 'memory benefits'
  ✓ Found 2 memories
    1. Tags: ['crewai', 'agentic_memory_research']
    2. Tags: ['crewai', 'agentic_memory_blog']

======================================================================
✅  Demo Complete!
======================================================================

🎯  Achievements:
    ✓ Research Agent stored findings
    ✓ Writer Agent retrieved findings 24h later
    ✓ Cross-session persistence verified
    ✓ Semantic search working

💡  Memanto enables long-term memory for CrewAI!
```

## 🏆 Bounty Requirements Checklist

- [x] Working Repository/Script with crewai + memanto
- [x] Memory Test Use Case (Research → Writer cross-session)
- [x] Visual Proof (terminal recording in demo)
- [x] How-To README (this file!)

### Bonus Points
- [ ] Integration with Cursor or n8n
- [x] Handling contradictory memories (Memanto's update capability)
- [ ] X thread demonstrating the project

## 📁 Files

- `demo_simple.py` - Main implementation (standalone, no external deps)
- `crewai_memanto_example.py` - Full CrewAI integration example
- `requirements.txt` - Python dependencies
- `README.md` - This documentation

## 🤝 Credits

- **CrewAI**: [https://crewai.io](https://crewai.io)
- **Memanto**: [https://github.com/moorcheh-ai/memanto](https://github.com/moorcheh-ai/memanto)
- **Bounty**: moorcheh-ai/memanto #37 ($100)

## 📝 License

MIT License - Same as Memanto project
