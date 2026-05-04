# CrewAI + Memanto: Persistent Agent Memory

This example shows how to give CrewAI agents **permanent, cross-session memory** using Memanto — solving the "long-term amnesia" problem where agents forget everything between runs.

## The Problem

Standard CrewAI agents reset their memory after every run. A research agent's findings are lost the moment the script exits. A writer agent can't build on yesterday's research.

## The Solution

Memanto acts as a **shared persistent memory layer**:

```
Session 1 (Tuesday):
  ResearchAgent → finds 5 key facts → stores in Memanto

Session 2 (Wednesday):
  WriterAgent → retrieves from Memanto → writes report
  (No re-research needed. Findings persist.)
```

## Quick Start

### 1. Install dependencies

```bash
pip install crewai memanto
```

### 2. Set up Memanto

```bash
# Configure your Moorcheh API key
memanto
```

### 3. Run the demo

```bash
# Session 1: Research agent stores findings
python crewai_memanto_example.py --mode research --topic "large language models in production"

# Session 2: Writer agent retrieves findings (run anytime — even days later)
python crewai_memanto_example.py --mode write --topic "large language models in production"

# Run both phases back-to-back
python crewai_memanto_example.py --mode both

# Bonus: Demo contradictory memory handling
python crewai_memanto_example.py --mode contradiction
```

## How It Works

### Memory Bridge

Three CrewAI tools wrap the Memanto CLI:

| Tool | Description |
|------|-------------|
| `remember` | Store a finding as a persistent memory |
| `recall` | Search memories by natural language query |
| `ask_memory` | Ask a question, get synthesized answer |

```python
class RememberTool(BaseTool):
    def _run(self, input_str: str) -> str:
        data = json.loads(input_str)
        return self.memory.remember(data["content"], data["type"], data.get("tags", ""))

class RecallTool(BaseTool):
    def _run(self, query: str) -> str:
        return self.memory.recall(query, limit=10)
```

### Shared Agent ID

Both the Research Agent and Writer Agent use the **same `agent_id`** in Memanto. This creates a shared memory pool:

```python
memory = MemantoMemory("crewai-demo-agent")  # shared ID

researcher = Agent(..., tools=[RememberTool(memory=memory)])
writer     = Agent(..., tools=[RecallTool(memory=memory)])
```

### Replacing Default CrewAI Memory

Standard CrewAI uses ephemeral in-process memory. To swap it for Memanto:

1. **Remove** `memory=True` from `Crew()`
2. **Add** `RememberTool` and `RecallTool` to your agents
3. **Initialize** `MemantoMemory` with a stable agent ID

```python
# Before (ephemeral)
crew = Crew(agents=[...], tasks=[...], memory=True)

# After (persistent via Memanto)
mem = MemantoMemory("my-agent")
agents = [Agent(..., tools=[RememberTool(mem), RecallTool(mem)])]
crew = Crew(agents=agents, tasks=[...])  # no memory=True needed
```

## Bonus: Contradictory Memory Handling

Memanto updates stale facts when newer, higher-confidence memories contradict them:

```python
# Old fact (will be superseded)
memory.remember("Python 3.9 is the latest version", type="fact")

# Correction stored with higher confidence
memory.remember(
    "Python 3.13 is the latest stable version. Previous belief outdated.",
    type="learning",
    tags="correction"
)

# Memanto surfaces the correction
memory.answer("What is the latest Python version?")
# → "Python 3.13..."
```

## Architecture

```
CrewAI Agent
    ↓ calls tool
RememberTool / RecallTool / AskMemoryTool
    ↓ subprocess
Memanto CLI (memanto remember / recall / answer)
    ↓ HTTP
Memanto API (moorcheh.ai)
    ↓ stores
Persistent Memory Store
```

## Example Output

```
=== Phase 1: Research Agent ===
[ResearchAgent] Storing finding: "LLMs require substantial GPU memory for inference..."
[RememberTool] ✓ Stored memory (id: mem_abc123)
[ResearchAgent] Storing finding: "Quantization reduces memory by 4-8x with minimal quality loss..."
...

=== Phase 2: Writer Agent (next day) ===
[WriterAgent] Recalling memories about "large language models in production"...
[RecallTool] Found 5 relevant memories from yesterday's research
[WriterAgent] Writing report...

## LLMs in Production: A Technical Overview

**Overview**: Large language models in production environments require...
```

## Requirements

- Python 3.9+
- `crewai >= 0.80.0`
- `memanto >= 0.1.0`
- Moorcheh API key (`memanto` to configure)
