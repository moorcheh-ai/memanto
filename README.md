<p align="center">
    <a href="https://www.memanto.ai/">
    <img alt="MEMANTO Logo" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="500">
    </a>
</p>

<div align="center">
  <h1>Your agents focus. Memanto remembers.</h1>
</div>

<h2 align="center">
  <em>A companion memory agent with its own intelligence that keeps your agents focused on their tasks.</em>
</h2>

<p align="center">
  Persistent memory for Claude Code, Cursor, Codex, and 14+ other agents, built on the world's first information-theoretic search engine. 100% free, open source, and runs entirely on your machine - no API keys, no vector database, no backend to babysit.
</p>

<p align="center">
  <a href="https://discord.gg/CyxRFQSQ3p">
    <img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord">
  </a>
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
    <img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Setup Video">
  </a>
  <a href="https://docs.memanto.ai">
    <img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Docs">
  </a>
</p>

<p align="center">
    <a href="https://pepy.tech/projects/memanto"><img alt="PyPI - Total Downloads" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
    <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="Ask DeepWiki" src="https://deepwiki.com/badge.svg"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
    <a href="https://pypi.org/project/memanto/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
    <a href="https://x.com/moorcheh_ai" target="_blank"><img src="https://img.shields.io/twitter/url/https/twitter.com/langchain.svg?style=social&label=Follow%20%40Moorcheh.ai" alt="Twitter / X"></a>
</p>


<p align="center"><a href="https://trendshift.io/repositories/27378" target="_blank"><img src="https://trendshift.io/api/badge/repositories/27378" alt="moorcheh-ai%2Fmemanto | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a></p>

<p align="center">
  <a href="https://www.star-history.com/?repos=moorcheh-ai%2Fmemanto&type=date&legend=top-left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&theme=dark&legend=top-left" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&legend=top-left" />
    <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=moorcheh-ai/memanto&type=date&legend=top-left" />
  </picture>
  </a>
</p>



---
## What Is MEMANTO?

**MEMANTO is a memory agent. It remembers, recalls, and answers — so your agents can achieve long-term goals and avoid confusion.**

Most memory tools today are passive infrastructure: agents have to query them, parse the results, and figure out what to do next. MEMANTO is built differently. It's an active memory agent designed from the gaps agents themselves named when asked about their memory — three operations (`remember`, `recall`, `answer`) that give your agents persistent context across sessions, with state-of-the-art retrieval and zero ingestion latency.

<div align="center">
  <h1>Memanto in action</h1>
  <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin: 20px 0;">
    <div style="text-align: center;">
      <h2 style="margin-top: 8px;">Without Memanto</strong></h2>
      <img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Before.gif" alt="Before" width="1100" style="border-radius: 8px;">
    </div>
    <div style="text-align: center;">
        <h2 style="margin-top: 8px;">With Memanto Connected</strong></h2>
        <img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/After.gif" alt="After" width="1100" style="border-radius: 8px;">
    </div>
  </div>
</div>

## Get started in 2 minutes

Works on macOS, Linux, and Windows.

**Option A — Fully local (no account, no API key):**
```bash
pip install memanto
memanto           # choose "On-Prem" — guides through Docker + Ollama setup
```
Requires Docker. Everything runs and stays on your machine.

**Option B — Free cloud (no card, ~60 seconds):**
```bash
pip install memanto
memanto           # choose "Cloud" — paste your free Moorcheh API key
```
Get your free API from : https://console.moorcheh.ai/api-keys

Switch between local and cloud at any time with `memanto config backend`.

---

## What you get

- **No more re-explaining your codebase** after every context reset. Memanto persists across sessions, your agent picks up where it left off.
- **Fewer tokens burned on repeated context.** Memories are retrieved only when relevant, so context windows go further.
- **Memories searchable the instant they're stored.** Zero indexing wait, no LLM extraction tax at write time.
- **One `pip install`.** No vector DB to provision, no schema, no rerankers, no backend service to babysit.
- **Zero idle cost.** Cloud scales to zero when not in use. On-prem runs only when you use it.

---

## Integrations

Works with Claude Code, Cursor, Codex, Windsurf, Cline, Continue, Goose, GitHub Copilot, and more. See the [full list →](https://docs.memanto.ai/integrations/overview)

```bash
memanto connect <integration-tool-id> # integrates in one command
#eg: memanto connect claude-code    
```

---

## The Six Gaps

Most memory tools are passive infrastructure — agents have to query them, parse the results, and figure out what to do. Memanto is an active memory agent built from the gaps models themselves named:

| # | Gap | What MEMANTO does about it |
| --- | --- | --- |
| 1 | **Static injection** — memory arrives as a blob, not queryable by relevance | Queryable, not injectable |
| 2 | **No temporal decay** — a preference from 6 months ago weighs the same as yesterday's deadline | Versioning, recency signals, temporal queries |
| 3 | **No provenance** — can't tell explicit facts from inferred patterns or outdated info | Confidence + provenance metadata on every memory |
| 4 | **Flat memory** — episodic, semantic, and procedural all collapsed to one layer | Typed and hierarchical — 13 built-in memory categories |
| 5 | **No writeback** — contradictions silently coexist | Conflict detection, explicit versioning, no silent overwrites |
| 6 | **Indexing delay** — mandatory LLM extraction, graph construction bottleneck | Zero-overhead ingestion, available at write time |


> *"My memory exists as a static snapshot injected into context — useful, but fundamentally passive."* — A model quote that became Memanto's design brief.

---

## Benchmarks

- **89.8% on LongMemEval** and **87.1% on LoCoMo** — outperforming Mem0, Zep, and Letta. [Public datasets →](https://huggingface.co/moorcheh)
- **Three primitives, not two**: `remember`, `recall`, and `answer`  LLM-grounded responses from memory, no extra API key.
- **Single-query retrieval.** No multi-stage pipelines, no graph schema, no rerankers.
- **Typed semantic memory.** 13 categories — `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship`, and more.

---

## Architecture

Memanto's retrieval is powered by [Moorcheh](https://moorcheh.ai), an information-theoretic semantic engine. It runs as a local Docker container (free, no account) or as a free cloud service (100K free operations) the `memanto` CLI manages either for you.

<p align="center">
  <img alt="MEMANTO architecture" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="1000">
</p>

### On-Prem

<p align="center">
  <img alt="MEMANTO architecture" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="1000">
</p>

---

## Why Moorcheh?

Moorcheh is the semantic engine behind Memanto's retrieval. Unlike vector databases that rely on approximate search and require indexing pipelines, Moorcheh uses an information-theoretic approach that returns exact results with zero indexing delay, write a memory and it's searchable immediately.

This means Memanto doesn't need a separate vector DB, embedding pipeline, or reranking stage. The Moorcheh engine runs as a local Docker container for on-prem users (no account needed) or as a managed cloud service with a free tier. Either way, it's invisible - the `memanto` CLI handles it.

---

## Setup & Demo

<p align="center">
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
    <img src="https://img.youtube.com/vi/vEtOaoweIG4/0.jpg" alt="Watch the video">
  </a>
</p>

---

## CLI Reference

| Capability | Commands | What it does |
|---|---|---|
| System status dashboard | `memanto status` | View environment, configuration, server health, active session, and registered agents. |
| Local REST API + Web UI | `memanto serve`, `memanto ui` | Run the MEMANTO REST API locally and open an interactive browser UI. (Optional for CLI usage). |
| Agent lifecycle management | `memanto agent ...` | Create/list/delete agents, activate/deactivate sessions, and run `agent bootstrap` for an intelligence snapshot. |
| Memory capture at scale | `memanto remember` | Store single memories, batch-ingest from JSON, or `--from-conversation` to automatically extract facts from chat logs. |
| Single-memory deletion | `memanto forget` | Delete one bad or outdated memory from the active agent after confirmation, or without the prompt with `--force`. |
| File upload to memory | `memanto upload` | Upload documents (.pdf, .docx, .xlsx, .json, .txt, .csv, .md) directly into an agent's memory namespace — content becomes instantly searchable via `recall`. |
| Advanced retrieval modes | `memanto recall` | Run standard search plus temporal queries (`--as-of`, `--changed-since`) with filters. |
| Grounded QA over memory | `memanto answer` | Generate RAG answers using retrieved memory context. |
| Daily intelligence workflows | `memanto daily-summary`, `memanto conflicts` | Generate summaries, detect contradictions, and resolve conflicts interactively. |
| Session and automation controls | `memanto session ...`, `memanto schedule ...` | Inspect sessions and enable scheduled daily summary runs. |
| Memory file pipelines | `memanto memory export`, `memanto memory sync` | Export structured memory markdown and sync `MEMORY.md` into projects. |
| Configuration inspection | `memanto config show` | Inspect API key status, active agent/session, server settings, and schedule time. |
| Multi-agent ecosystem integration | `memanto connect ...` | Connect/remove/list integrations for Claude Code, Codex, Cursor, Windsurf, Antigravity, Gemini CLI, Cline, Continue, OpenCode, Goose, Roo, GitHub Copilot, and Augment (local or global). |

For a complete command reference, see the [CLI User Guide](https://docs.memanto.ai/cli).

### Supported Memory Types

`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

Use memory types to categorize what you store so retrieval is cleaner and more controllable:
- Save with a specific type: `memanto remember "User prefers concise answers" --type preference`
- Filter by type when searching: `memanto recall "user communication style" --type preference`

---

## 📦 SDKs

- **TypeScript / Node.js** — [`@moorcheh-ai/memanto`](sdks/typescript) — boots a local Memanto server via `uvx` and exposes an ergonomic `Memanto` client (`remember` / `recall` / `answer`).

---

## REST API

Memanto exposes a session-based REST API for programmatic access. Start the server locally:

```bash
memanto serve
```

Full endpoint reference is available at [docs.memanto.ai/api](https://docs.memanto.ai/api) and at `http://localhost:8000/docs` when the server is running.

---

## Research

[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://huggingface.co/papers/2604.22085)

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

## Support

Have questions or feedback? We're here to help:
- **Docs**: [https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**: [Join our Discord server](https://discord.gg/CyxRFQSQ3p)
- **Email**: support@moorcheh.ai
- **X / Twitter**: [@moorcheh_ai](https://x.com/moorcheh_ai)

---

**MIT License**
