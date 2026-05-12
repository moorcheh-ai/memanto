# Memanto × LangGraph Integration

**Repository**: [moorcheh-ai/memanto](https://github.com/moorcheh-ai/memanto) | [Examples Index](https://github.com/moorcheh-ai/memanto/tree/main/examples)

A LangGraph tool suite that wraps the Memanto SDK, enabling persistent, cross-agent memory operations within LangGraph agent pipelines.

---

## Overview

This integration exposes three Memanto tools as LangGraph-compatible components:

| Tool | Method | Purpose |
|------|--------|---------|
| `MemantoRememberTool` | `remember` | Store structured memories with type, title, content, confidence, tags |
| `MemantoRecallTool` | `recall` | Semantic search over stored memories |
| `MemantoAnswerTool` | `answer` | RAG-based Q&A grounded in agent memory |

These tools let LangGraph agents maintain persistent memory that survives across sessions and can be shared between agents.

---

## Installation

```bash
pip install memanto langgraph-sdk
```

---

## Quick Start

```python
from memanto_langgraph import create_memanto_tools
from memanto.cli.client.sdk_client import SdkClient

client = SdkClient(api_key="your-memanto-api-key")
agent_id = "my-langgraph-agent"

tools = create_memanto_tools(client, agent_id)

# tools["remember"] → MemantoRememberTool
# tools["recall"]  → MemantoRecallTool
# tools["answer"]  → MemantoAnswerTool
```

Or use `MemantoSetup` for full agent lifecycle management:

```python
from memanto_langgraph import MemantoSetup

setup = MemantoSetup(api_key="your-api-key")
client = setup.setup(agent_id="my-agent", description="LangGraph agent")

# ... run your graph ...

setup.teardown("my-agent")
```

---

## Demo / Cross-Session Example

See [`examples/langgraph-memanto/`](../../examples/langgraph-memanto/) for a complete cross-session memory demo:

1. `run_research.py` — stores research findings in Session 1
2. `run_recall.py` — recalls those findings in Session 2 (cross-session persistence)

A 30-second demo GIF is available in the example README.

---

## Payment / Bounty Wallets

- **EVM (ETH, BASE, etc.):** `0x04836c595d9633abeb120b7b68f57e6e834b0c6c`
- **SOL (Solana):** `9r7u8mET3M5rvDf4txqzkMsvaGXk9BUoNtZNZfv685VB`

---

## License

MIT — see [moorcheh-ai/memanto](https://github.com/moorcheh-ai/memanto)