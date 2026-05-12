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

**MEMANTO is a memory agent. It remembers, recalls, and answers — so your agents can achieve long-term goals and avoid confusion.**

Most memory tools today are passive infrastructure: agents have to query them, parse the results, and figure out what to do next. MEMANTO is built differently. It's an active memory agent designed from the gaps agents themselves named when asked about their memory — three operations (`remember`, `recall`, `answer`) that give your agents persistent context across sessions, with state-of-the-art retrieval and zero ingestion latency.

> *"My memory exists as a static snapshot injected into context — useful, but fundamentally passive. I can't query it, update it mid-conversation, express confidence levels, or distinguish between 'I know this' versus 'I was told this once.'"*
>
> — A representative model reply that became MEMANTO's design brief.

We unpacked that into six concrete gaps and built MEMANTO to solve all six.

### The Six Gaps

| # | Gap | What MEMANTO does about it |
| --- | --- | --- |
| 1 | **Static injection** — memory arrives as a blob, not queryable by relevance | Queryable, not injectable |
| 2 | **No temporal decay** — a preference from 6 months ago weighs the same as yesterday's deadline | Versioning, recency signals, temporal queries |
| 3 | **No provenance** — can't tell explicit facts from inferred patterns or outdated info | Confidence + provenance metadata on every memory |
| 4 | **Flat memory** — episodic, semantic, and procedural all collapsed to one layer | Typed and hierarchical — 13 built-in memory categories |
| 5 | **No writeback** — contradictions silently coexist | Conflict detection, explicit versioning, no silent overwrites |
| 6 | **Indexing delay** — mandatory LLM extraction, graph construction bottleneck | Zero-overhead ingestion, available at write time |

## Why MEMANTO Performs

MEMANTO is built for teams that want SOTA agent memory without graph-heavy complexity. It pairs a typed semantic memory schema with [Moorcheh's](https://moorcheh.ai/) information-theoretic retrieval engine — a no-indexing semantic database that delivers exact search, sub-90ms retrieval, and zero ingestion delay.

* **State-of-the-art benchmarks**: **89.8% on LongMemEval** and **87.1% on LoCoMo** — outperforming Mem0, Mem0g, Zep, and Letta on both. [Public datasets on Hugging Face](https://huggingface.co/moorcheh).
* **Three primitives, not two**: `remember`, `recall`, and `answer` — LLM-grounded responses generated directly from your agent's memory, with no extra API key.
* **Zero ingestion latency**: No indexing wait, no LLM extraction tax at write time. Memories are searchable the instant they're stored.
* **Zero idle cost**: Serverless architecture scales to zero when not in use.
* **Single-query retrieval**: One call. No multi-stage pipelines, no graph schema to maintain, no rerankers to wire up.
* **Typed semantic memory**: 13 built-in memory categories — `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship`, and more — for cleaner retrieval and contradiction detection.

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
| Advanced retrieval modes | `memanto recall` | Run standard search plus temporal queries (`--as-of`, `--changed-since`) with filters. |
| Grounded QA over memory | `memanto answer` | Generate RAG answers using retrieved memory context. |
| Daily intelligence workflows | `memanto daily-summary`, `memanto conflicts` | Generate summaries, detect contradictions, and resolve conflicts interactively. |
| Session and automation controls | `memanto session ...`, `memanto schedule ...` | Inspect sessions and enable scheduled daily summary runs. |
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
- `DELETE /api/v2/agents/{agent_id}` - Delete local agent metadata (`?delete-backup-too=true` also deletes Moorcheh namespace backup)

### Session Management
- `POST /api/v2/agents/{agent_id}/activate` - Start a session (returns a 6-hour JWT `session_token`)
- `POST /api/v2/agents/{agent_id}/deactivate` - Manually end a session
- `GET /api/v2/agents/{agent_id}/status` - Check active session status for an agent

### Memory Operations
- `POST /api/v2/agents/{agent_id}/remember` - Store a new memory into the agent's semantic database
- `POST /api/v2/agents/{agent_id}/batch-remember` - Batch-store up to 100 memories in one request
- `POST /api/v2/agents/{agent_id}/upload-file` - Upload a file (.pdf, .docx, .xlsx, .json, .txt, .csv, .md) — content is chunked and made searchable
- `POST /api/v2/agents/{agent_id}/recall` - Run an exact semantic search against the agent's memories
- `POST /api/v2/agents/{agent_id}/answer` - Generate a grounded RAG answer based on the agent's memories

**Authentication Required:**
- Server-side `MOORCHEH_API_KEY` must be configured in MEMANTO
- `X-Session-Token: {session_token}` header (for session-scoped and memory operations)

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

## 📞 Support & Documentation

Have questions or feedback? We're here to help:
- **Docs**: [https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**: [Join our Discord server](https://discord.gg/CyxRFQSQ3p)
- **Email**: support@moorcheh.ai

---

**MIT License**
