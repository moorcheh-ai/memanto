# LangGraph + Memanto: Give Your Graph a Permanent Brain 🧠

[![LangGraph](https://img.shields.io/badge/LangGraph-v0.3+-blue)](https://github.com/langchain-ai/langgraph)
[![Memanto](https://img.shields.io/badge/Memanto-v0.1+-purple)](https://github.com/moorcheh-ai/memanto)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **A working example of Memanto as the long-term memory layer for a LangGraph agent, with full cross-session recall.**

![Demo GIF](https://via.placeholder.com/800x450/1a1a2e/e94560?text=LangGraph+Memanto+Demo+-+See+PR+description+for+video+link)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   LangGraph Agent                         │
│  ┌──────────┐   ┌────────────┐   ┌──────────────────┐    │
│  │  Input    │──▶│  Reasoning │──▶│  Action/Tool     │    │
│  │  Node     │   │  Node      │   │  Node            │    │
│  └──────────┘   └─────┬──────┘   └────────┬─────────┘    │
│                       │                   │               │
│                       ▼                   ▼               │
│              ┌──────────────────────────────┐             │
│              │     Memanto Memory Layer      │             │
│              │  ┌────────┐ ┌────────┐ ┌───┐ │             │
│              │  │remember│ │ recall │ │ans │ │             │
│              │  └───┬────┘ └───┬────┘ └─┬─┘ │             │
│              └──────┼──────────┼────────┼───┘             │
│                     │          │        │                  │
│                     ▼          ▼        ▼                  │
│              ┌──────────────────────────────┐             │
│              │      Moorcheh Database        │             │
│              │   (Semantic Search Engine)    │             │
│              └──────────────────────────────┘             │
└─────────────────────────────────────────────────────────┘
```

## ✨ What This Demonstrates

| Feature | Description |
|---------|-------------|
| **Cross-Session Recall** | The agent remembers facts from previous conversations that aren't in the current state |
| **Typed Memory** | Uses Memanto's 13 built-in memory categories (facts, preferences, decisions, etc.) |
| **Semantic Search** | Retrieves memories by meaning, not just keywords |
| **Provenance Tracking** | Every memory has confidence, source, and timestamp metadata |
| **Temporal Awareness** | Recency-weighted retrieval with point-in-time queries |

## 🚀 Quick Start

### 1. Prerequisites

```bash
python >= 3.10
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Memanto

Memanto runs as a standalone service. Copy the `.env.example` and configure:

```bash
cp .env.example .env
# Edit .env with your MOORCHEH_API_KEY (get one at https://moorcheh.ai)
```

Then start the Memanto server:

```bash
# From the memanto repo root:
docker-compose up -d
# Or run directly:
python -m memanto
```

### 4. Run the Demo

```bash
python run_demo.py
```

The demo will:
1. **Session 1**: The agent learns the user's preferences and remembers them
2. **Session 1 ends** (state is discarded)
3. **Session 2**: The agent recalls the user's preferences from Memanto — **cross-session recall!**

## 🔬 How Cross-Session Recall Works

The magic happens in the `MemantoMemory` class:

```python
class MemantoMemory:
    """Long-term memory backed by Memanto API."""

    def _call_api(self, endpoint: str, payload: dict) -> dict:
        """Call the Memanto REST API."""
        resp = requests.post(
            f"{self.base_url}/api/v2/agents/{self.agent_id}/{endpoint}",
            headers={"X-Session-Token": self.session_token},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def remember(self, content: str, memory_type: str, **metadata) -> str:
        """Store a memory."""
        payload = {
            "type": memory_type,
            "title": metadata.get("title", content[:80]),
            "content": content,
            **metadata,
        }
        result = self._call_api("remember", payload)
        return result.get("id")

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve memories by semantic similarity."""
        result = self._call_api("recall", {"query": query, "limit": limit})
        return result.get("results", [])

    def answer(self, query: str) -> str:
        """Get an LLM-grounded answer from memory."""
        result = self._call_api("answer", {"query": query})
        return result.get("answer", "")
```

**The key insight:** During `Session 1`, the agent calls `memory.remember()` which stores facts in Memanto's Moorcheh-backed database. When `Session 2` starts, a completely fresh LangGraph state is initialized — but the agent calls `memory.recall()` to retrieve memories from the previous session. The memories persist because they live outside the LangGraph state, in Memanto's database.

## 📁 File Structure

```
examples/langgraph-memanto/
├── README.md            ← You are here
├── requirements.txt     ← Python dependencies
├── .env.example         ← Environment config template
├── agent.py             ← LangGraph agent + Memanto integration
└── run_demo.py          ← Demo script (cross-session recall)
```

## 📊 Social Traction

If you find this useful, please:
- ⭐ Star the [Memanto repo](https://github.com/moorcheh-ai/memanto)
- 🐦 Post on X with **#Memanto** and tag **@moorcheh_ai**
- 💬 Share on Reddit with your feedback

## 📝 License

MIT — See [LICENSE](../../LICENSE) for details.
