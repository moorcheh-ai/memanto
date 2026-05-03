<p align="center">
    <a href="https://www.memanto.ai/">
    <img alt="MEMANTO Logo" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-dark.svg" width="500">
    </a>
</p>

<div align="center">
  <h1>Memanto - Memory that AI Agents Love!</h1>
</div>

<p align="center">
  <a href="https://memanto.ai/">
    <img src="https://img.shields.io/badge/Learn-More-000000?style=for-the-badge&logo=rocket&logoColor=white" alt="Learn More">
  </a>
  <a href="https://discord.gg/CyxRFQSQ3p">
    <img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord">
  </a>
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
    <img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Setup Video">
  </a>
</p>

<p align="center">
    <a href="https://pypi.org/project/memanto/"><img alt="PyPI - Total Downloads" src="https://img.shields.io/pepy/dt/memanto.svg?color=blue&label=downloads"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
    <a href="https://pypi.org/project/memanto/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
    <a href="https://x.com/moorcheh_ai" target="_blank"><img src="https://img.shields.io/twitter/url/https/twitter.com/langchain.svg?style=social&label=Follow%20%40Moorcheh.ai" alt="Twitter / X"></a>
</p>

---

## What Is MEMANTO?

MEMANTO is a universal memory layer for agentic AI. While LLMs often forget context between sessions, MEMANTO gives your agents long-term memory so they can carry context forward and remember what matters across sessions.

## Why MEMANTO Performs

MEMANTO is built for teams that want high-quality agent memory without graph-heavy complexity. It combines immediate semantic availability, low-overhead serverless operation, and strong real-world memory accuracy so you can ship production workflows with a simpler architecture.

- **Zero-cost ingestion latency**: No indexing wait or token usage at ingestion, so memories are available for retrieval immediately.
- **Zero storage cost at idle**: Serverless architecture scales to zero when not in use.
- **State-of-the-art benchmark performance**: Final evaluation results reached **89.8% on LongMemEval** and **87.1% on LoCoMo**.

## 🏗️ Architecture

<img alt="MEMANTO architecture" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="1000">

## 📺 Setup & Demo

[![Watch the video](https://img.youtube.com/vi/vEtOaoweIG4/0.jpg)](https://www.youtube.com/watch?v=vEtOaoweIG4)

## 🚀 MEMANTO CLI

MEMANTO comes with a powerful, developer-friendly Command Line Interface. You can manage your agent's memories completely from your terminal—no local server required!

You need a Moorcheh API key to use MEMANTO. Create one in the [Moorcheh Dashboard](https://console.moorcheh.ai/api-keys).

MEMANTO has native LLM access, so you don't need a separate external model API key for common memory workflows.

### 1. Install & Configure
```bash
pip install memanto

# Setup your environment (prompts for your Moorcheh API key)
memanto
```

### 2. Test Agent Memories
```bash
# Create and auto-activate an agent session
memanto agent create customer-support

# Store memories with specific semantic types
memanto remember "The user prefers dark mode for the dashboard."
memanto remember "User's timezone is PST."

# Instantly recall relevant context
memanto recall "What mode does the user like?"

# Get grounded AI answers using built-in RAG
memanto answer "Based on the memory, what should the theme be set to?"
```

### Supported Memory Types

`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

Use memory types to categorize what you store so retrieval is cleaner and more controllable:
- Save with a specific type: `memanto remember "User prefers concise answers" --type preference`
- Filter by type when searching: `memanto recall "user communication style" --type preference`

---

### Key Features
| Capability | Commands | What it does |
|---|---|---|
| System status dashboard | `memanto status` | View environment, configuration, server health, active session, and registered agents. |
| Local REST API + Web UI | `memanto serve`, `memanto ui` | Run the MEMANTO REST API locally and open an interactive browser UI. (Optional for CLI usage). |
| Agent lifecycle management | `memanto agent ...` | Create/list/delete agents, activate/deactivate sessions, and run `agent bootstrap` for an intelligence snapshot. |
| Memory capture at scale | `memanto remember` | Store single memories with metadata or batch-ingest up to 100 records from JSON. |
| File upload to memory | `memanto upload` | Upload documents (.pdf, .docx, .xlsx, .json, .txt, .csv, .md) directly into an agent's memory namespace — content becomes instantly searchable via `recall`. |
| Advanced retrieval modes | `memanto recall` | Run standard search plus temporal queries (`--as-of`, `--changed-since`, `--current-only`) with filters. |
| Grounded QA over memory | `memanto answer` | Generate RAG answers using retrieved memory context. |
| Daily intelligence workflows | `memanto daily-summary`, `memanto conflicts` | Generate summaries, detect contradictions, and resolve conflicts interactively. |
| Session and automation controls | `memanto session ...`, `memanto schedule ...` | Inspect/extend sessions and enable scheduled daily summary runs. |
| Memory file pipelines | `memanto memory export`, `memanto memory sync` | Export structured memory markdown and sync `MEMORY.md` into projects. |
| Configuration inspection | `memanto config show` | Inspect API key status, active agent/session, server settings, and schedule time. |
| Multi-agent ecosystem integration | `memanto connect ...` | Connect/remove/list integrations for Claude Code, Codex, Cursor, Windsurf, Antigravity, Gemini CLI, Cline, Continue, OpenCode, Goose, Roo, GitHub Copilot, and Augment (local or global). |

Additional setup guides are available at the Moorcheh [YouTube channel](https://www.youtube.com/@moorchehai/videos).

---

## 🎯 REST API Endpoints

For programmatic access, MEMANTO exposes a clean, session-based REST API.

**Important:** MEMANTO does not have a hosted API server yet. To use these endpoints, run your own local server first:

```bash
cd memanto

# Start server
memanto serve

# Or run with Docker
docker-compose up -d
```

By default, call the endpoints on your local server (for example: `"http://127.0.0.1:8000"`).

### Agent Management
- `POST /api/v2/agents` - Create a new agent namespace
- `GET /api/v2/agents` - List all available agents
- `GET /api/v2/agents/{agent_id}` - Get metadata for a specific agent
- `DELETE /api/v2/agents/{agent_id}` - Delete an agent and all its memories

### Session Management
- `POST /api/v2/agents/{agent_id}/activate` - Start a session (returns a 6-hour JWT `session_token`)
- `POST /api/v2/agents/{agent_id}/deactivate` - Manually end a session
- `GET /api/v2/session/current` - Check the status/validity of the current session
- `POST /api/v2/session/extend` - Extend the session expiration time

### Memory Operations
- `POST /api/v2/agents/{agent_id}/remember` - Store a new memory into the agent's semantic database
- `POST /api/v2/agents/{agent_id}/batch-remember` - Batch-store up to 100 memories in one request
- `POST /api/v2/agents/{agent_id}/upload-file` - Upload a file (.pdf, .docx, .xlsx, .json, .txt, .csv, .md) — content is chunked and made searchable
- `GET /api/v2/agents/{agent_id}/recall` - Run an exact semantic search against the agent's memories
- `POST /api/v2/agents/{agent_id}/answer` - Generate a grounded RAG answer based on the agent's memories

**Authentication Required:**
- `Authorization: Bearer {moorcheh_api_key}` header
- `X-Session-Token: {session_token}` header (for Session & Memory operations)

---

## 🤖 Why Moorcheh?

**Moorcheh.ai** - The world's **only no-indexing semantic database**.

### The Revolutionary Difference

**Traditional Vector DBs**: Minutes of indexing delay, approximate search, stateful architecture

**Moorcheh**: Instant availability, exact search, serverless/stateless, 80% compute savings

### Real Impact

| Feature | Traditional | Moorcheh |
|---------|------------|----------|
| Write-to-Search | Minutes | **Instant** |
| Accuracy | Approximate | **Exact** |
| Idle Costs | Always running | **Zero** |
| Free Tier | Limited | **100K ops/month** |

---

## 📄 Research & Results

MEMANTO is backed by peer-reviewed research. For benchmark results, methodology, and technical details, see our paper on Hugging Face:

**[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://huggingface.co/papers/2604.22085)**

> 🌟 **If you find this project useful, please upvote the paper on Hugging Face!** It helps the research reach more people in the community.

You can also explore our models and resources on the **[Moorcheh Hugging Face organization page](https://huggingface.co/moorcheh)**.

If you use MEMANTO in your research, please cite:

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents}, 
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026},
      eprint={2604.22085},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085}, 
}
```

---

## 🔗 CrewAI Integration - Best-in-Class Memory for Agent Teams

We've built a best-in-class integration between CrewAI and Memanto's Agentic Memory. This integration allows CrewAI agents to use Memanto as their primary memory store, providing persistent, long-term memory with advanced features.

### Why Memanto is Better Than Standard Local Storage

1. **Persistent Long-Term Memory**: Unlike local storage that's limited to a single session, Memanto provides persistent memory across sessions and deployments.

2. **Advanced Memory Features**:
   - Vector-based retrieval of past thoughts
   - Memory validation and trust scoring
   - Temporal queries (as-of, changed-since)
   - Multi-scope memory organization

3. **Production-Ready Architecture**:
   - Serverless operation with zero idle costs
   - Instant availability of memories (no indexing delay)
   - High accuracy with exact search
   - Built-in RAG capabilities

4. **Structured Memory Types**: Memanto supports 14 different memory types (fact, preference, goal, etc.) that help organize and retrieve memories more effectively.

5. **Scalability**: Memanto can handle large volumes of memories efficiently, making it suitable for production use with multiple agents.

6. **Conflict Resolution**: Memanto has built-in mechanisms to detect and resolve memory contradictions.

7. **Daily Intelligence Workflows**: Automated daily summaries and conflict detection help maintain memory quality.

### How to Use the Integration

1. Install the required packages:
```bash
pip install crewai memanto
```

2. Set up your Memanto adapter:
```python
from memanto.integrations.crewai_adapter import MemantoCrewAdapter, MemantoCrewAdapterConfig

config = MemantoCrewAdapterConfig(
    moorcheh_api_key="your-moorcheh-api-key",
    default_scope_type="agent"
)
adapter = MemantoCrewAdapter(config)
```

3. Create a CrewAI memory instance with Memanto:
```python
from crewai.memory.unified_memory import Memory

memory = Memory(
    storage=adapter,
    llm="gpt-4o-mini"  # Use a capable LLM for memory analysis
)
```

4. Use the memory in your CrewAI agents:
```python
from crewai import Agent, Task, Crew

researcher = Agent(
    role="Research Analyst",
    goal="Uncover cutting-edge developments in AI",
    backstory="You're a seasoned research analyst...",
    memory=True  # Enable memory
)

crew = Crew(
    agents=[researcher],
    tasks=[...],
    memory=memory  # Use Memanto memory
)
```

### Example: Multi-Agent Crew with Memanto Memory

See the [crewai_integration.py](examples/crewai_integration.py) example for a complete demonstration of a multi-agent crew using Memanto memory.

### Files Modified/Created

1. Created new integration adapter:
   - `/memanto/integrations/crewai_adapter.py`

2. Created example demonstrating the integration:
   - `/examples/crewai_integration.py`

## 📞 Support & Documentation

Have questions or feedback? We're here to help:
- **Docs**: [https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**: [Join our Discord server](https://discord.gg/CyxRFQSQ3p)
- **Email**: support@moorcheh.ai

---

**MIT License**
