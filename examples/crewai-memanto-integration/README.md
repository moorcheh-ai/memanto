# CrewAI + MEMANTO Integration

A production-ready example showing how to replace CrewAI's default memory with MEMANTO's persistent, queryable agent memory layer.

## 🧠 What This Does

This integration demonstrates CrewAI agents using MEMANTO as their primary memory layer:

- **Research Agent**: Stores research findings in MEMANTO with type, confidence, and provenance metadata
- **Writer Agent**: Retrieves stored memories from a different session or agent to produce informed content
- **Memory Test**: Proves cross-session, cross-agent memory retrieval works seamlessly

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install crewai memanto python-dotenv
```

### 2. Get Your API Keys

1. Sign up at [Moorcheh Console](https://console.moorcheh.ai/api-keys) and create an API key
2. Create a `.env` file:

```env
MOORCHEH_API_KEY=your_moorcheh_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Or any LLM CrewAI supports
```

### 3. Activate Your MEMANTO Agent

```bash
# Activate the example agent
memanto agent activate crewai-memanto-demo
```

### 4. Run the Demo

```bash
python crewai_memanto_demo.py
```

## 🔄 How It Works

### Architecture

```
┌──────────────────┐        ┌──────────────────┐
│  Research Agent  │        │   Writer Agent   │
│  (Session 1)     │        │  (Session 2 /    │
│                  │        │   Different Run)  │
└───────┬──────────┘        └───────┬──────────┘
        │                           │
        │  remember()               │  recall()
        ▼                           ▼
┌──────────────────────────────────────────────┐
│               MEMANTO Memory Layer            │
│  • Typed memories (fact, preference, goal)   │
│  • Cross-session persistence                 │
│  • Confidence + provenance metadata          │
│  • Semantic search + temporal queries        │
└──────────────────────────────────────────────┘
```

### The Memory Test

1. **Run 1**: Research Agent stores findings about a topic in MEMANTO
2. **Run 2** (or later): Writer Agent retrieves those findings using semantic recall
3. **Verification**: The Writer Agent correctly references information from the Research Agent's session

## 🔧 Replacing Standard CrewAI Memory

To use MEMANTO instead of CrewAI's built-in memory:

### Before (CrewAI Default)

```python
from crewai import Agent, Task, Crew, Process

crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    process=Process.sequential,
    memory=True  # Uses CrewAI's default short-term memory
)
```

### After (With MEMANTO)

```python
from crewai import Agent, Task, Crew, Process
from memanto_memory import MemantoAgentMemory

# Replace CrewAI's memory with MEMANTO
memanto_memory = MemantoAgentMemory(agent_id="crewai-memanto-demo")

crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    process=Process.sequential,
    memory_config={
        "provider": memanto_memory,
        "type": "long_term"
    }
)
```

### The `MemantoAgentMemory` Class

```python
import subprocess
import json
import os

class MemantoAgentMemory:
    """Drop-in replacement for CrewAI memory using MEMANTO."""

    def __init__(self, agent_id: str = "crewai-agent"):
        self.agent_id = agent_id
        self._ensure_agent_active()

    def _ensure_agent_active(self):
        """Activate the MEMANTO agent session."""
        subprocess.run(
            ["memanto", "agent", "activate", self.agent_id],
            check=True, capture_output=True
        )

    def remember(self, content: str, memory_type: str = "fact",
                 tags: str = None, confidence: float = 0.9) -> bool:
        """Store a memory in MEMANTO."""
        cmd = [
            "memanto", "remember", content,
            "--type", memory_type,
            "--confidence", str(confidence),
            "--provenance", "agent_observation",
            "--source", self.agent_id
        ]
        if tags:
            cmd.extend(["--tags", tags])
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            return True
        except Exception as e:
            print(f"[MEMANTO] Error remembering: {e}")
            return False

    def recall(self, query: str, limit: int = 5) -> list:
        """Recall memories from MEMANTO."""
        try:
            result = subprocess.run(
                ["memanto", "recall", query, "--limit", str(limit), "--json"],
                check=True, capture_output=True, text=True, timeout=30
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return []
        except Exception as e:
            print(f"[MEMANTO] Error recalling: {e}")
            return []

    def answer(self, question: str) -> str:
        """Ask MEMANTO a question (RAG over memories)."""
        try:
            result = subprocess.run(
                ["memanto", "answer", question],
                check=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            return f"[MEMANTO] Error: {e}"
```

## 📦 Files

| File | Description |
|------|-------------|
| `crewai_memanto_demo.py` | Main demo script with Research + Writer agents |
| `memanto_memory.py` | `MemantoAgentMemory` class for drop-in replacement |
| `README.md` | This file |

## 🏆 Bonus Features

- ✅ **Cross-session memory**: Run the demo once, then run it again — Writer Agent remembers past research
- ✅ **Typed memories**: Uses MEMANTO's built-in types (fact, preference, goal, instruction)
- ✅ **Contradiction handling**: MEMANTO detects conflicting information and versions it
- ✅ **Confidence scoring**: Every memory stores confidence + provenance metadata

## 📹 Demo Recording

[asciinema recording coming soon]

## 📄 License

MIT
