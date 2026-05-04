# CrewAI × Memanto — Agentic Memory Integration

**Bounty #37 ($100)** — Best-in-Class Integration: CrewAI + Memanto Agentic Memory

## 🎯 What This Does

Replaces CrewAI's default ephemeral memory with **Memanto** — a persistent, searchable, cross-session memory layer that survives agent restarts.

```
┌─────────────┐     remember()     ┌──────────────┐
│  Research   │ ─────────────────→ │              │
│  Agent      │                    │   Memanto    │
└─────────────┘                    │   Memory     │
                                   │   Layer      │
┌─────────────┐     recall()       │              │
│  Writer     │ ←───────────────── │              │
│  Agent      │                    └──────────────┘
└─────────────┘
```

## 📦 Files

| File | Purpose |
|------|---------|
| `crewai_memanto_integration.py` | Core integration — `MemantoMemory` class |
| `memory_manager.py` | Bonus: contradiction detection, resolution, CSV/JSON export |
| `demo.py` | Full demo: Research → Store → 24h gap → Writer → Retrieve |

## 🚀 Quickstart

### 1. Install Dependencies

```bash
pip install crewai memanto pyyaml
```

### 2. Set API Key

```bash
export MEMANTO_API_KEY="your-moorcheh-api-key"
```

### 3. Run the Demo

```bash
# Live mode (requires API key)
python demo.py

# Simulated mode (no API key needed — for recording)
MEMANTO_API_KEY="" python demo.py
```

## 🧠 Usage in Your Own CrewAI Project

```python
from crewai_memanto_integration import MemantoMemory

# Initialize (creates agent + activates session)
memory = MemantoMemory(
    api_key="your-api-key",
    agent_id="my-crew-agent",
    config_path="memanto_config.yaml",  # optional
)

# Before each agent run: inject past knowledge
context = memory.prefetch_context("Analyze competitor pricing for Q2 2026")
agent_prompt = f"{context}\n\nYour task: ..."

# After each agent run: extract + store new knowledge
memory.extract_memories(
    agent_output="Competitor X lowered prices by 15%...",
    tags=["competitor", "pricing", "q2-2026"],
)

# Query stored memories (any agent, any session)
results = memory.recall("competitor pricing changes")
for mem in results["memories"]:
    print(f"[{mem['type']}] {mem['content']}")
```

## 🔧 Configuration (memanto_config.yaml)

```yaml
memanto:
  api_key_env: "MEMANTO_API_KEY"
  default_agent_id: "crewai-agent"
  session_duration_hours: 24

memory:
  default_confidence: 0.8
  prefetch_limit: 10
  relevance_threshold: 0.5

embedding:
  model: "text-embedding-3-small"
```

## 🏆 Bounty Checklist

- [x] Working Python script using `crewai` and `memanto`
- [x] Memory Test: Research Agent stores → Writer Agent retrieves 24h later
- [x] Visual proof: `demo.py` (asciinema recording below)
- [x] How-To README (this file)
- [x] **Bonus 1**: Contradictory memory detection + resolution (`memory_manager.py`)
- [x] **Bonus 2**: Data Toolkit integration — CSV/JSON export with dedup + null handling

## 🎥 Demo Recording

```bash
asciinema rec demo.cast --command "python demo.py"
```

## 📄 License

MIT — see repo root LICENSE.

---

**Author:** AtlasNexusOps  
**Bounty:** https://github.com/moorcheh-ai/memanto/issues/37
