<p align="center">
    <a href="https://www.memanto.ai/">
    <img alt="MEMANTO Logo" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="500">
    </a>
</p>

<h2 align="center">
  <em>Memanto is a companion Memory Agent; an agent whose whole job is managing your other agents' memories.</em>
</h2>
<p align="center"> <strong>⭐ Star the repo</strong> if Memanto is helping your agentic fleet. </p> <p align="center">

<p align="center">
   It curates what's worth keeping, consolidates it across sessions, and briefs your agents the moment they need it, while you keep ownership of everything they learn. Works automatically with Claude Code, Cursor, Codex, and 20+ other agents. Fully convertible between semantic backend and Open Knowledge Format (*.md files in llm wiki style), so your memory estate is yours to inspect, export, and migrate anywhere — <code>memanto migrate</code> and it moves with you.
</p>

<p align="center">
  <code>pip install memanto</code>
</p>


<p align="center">
    <a href="https://pepy.tech/projects/memanto"><img alt="PyPI - Total Downloads" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
    <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="Ask DeepWiki" src="https://deepwiki.com/badge.svg"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
    <a href="https://pypi.org/project/memanto/"><img alt="PyPI Version" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
    <a href="https://x.com/moorcheh_ai" target="_blank"><img src="https://img.shields.io/twitter/url/https/twitter.com/langchain.svg?style=social&label=Follow%20%40Moorcheh.ai" alt="Twitter / X"></a>
</p>

<p align="center"><a href="https://mcptoplist.com/server/glama%2Fmoorcheh-ai%2Fmemanto"><img src="https://mcptoplist.com/badge/glama%2Fmoorcheh-ai%2Fmemanto.svg" alt="mcp top list" width="250" height="30"></a></p>
<p align="center"><a href="https://trendshift.io/repositories/27378" target="_blank"><img src="https://trendshift.io/api/badge/repositories/27378" alt="moorcheh-ai%2Fmemanto | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a></p>


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

### Your fleet of agents start working 

**One memory, shared across the fleet.**
Your Cursor session doesn't know what Claude Code decided this morning. Your review agent doesn't know what your test agent already tried and rejected. Memanto gives them one shared memory; what any agent learns, every agent knows.

**Every agent starts briefed.**
`memanto agent bootstrap` hands a new agent an intelligence snapshot of what the fleet already knows: the decisions, the constraints, the things that were tried and reversed. No warm-up prompt. No context-loading ritual before real work starts.

**Scoped memory per agent.**
Each agent gets its own namespace, so your production-ops agent isn't reading your scratch experiments. Provision exactly what each one should know; nothing more.

### The fleet gets smarter without you baby sitting it

**Consolidation runs on schedule.**
`memanto schedule` runs daily: new memories curated, duplicates merged across agents, contradictions flagged for review. You come back to a fleet that knows more than it did yesterday, without having sorted anything yourself.

**Contradictions surface instead of compounding.**
Two agents learn opposite things about the same system. `memanto conflicts` catches it, versions both, and brings it to you; rather than letting whichever wrote last silently win and propagate to everything downstream.

**Memory that knows *when*.**
Query what the fleet knew last Tuesday (`--as-of`), or what changed since your last release (`--changed-since`). A preference from six months ago doesn't outrank yesterday's deadline.

### See what your fleet knows

**Full visibility over the memory estate.**
`memanto status` for registered agents, active sessions, and server health. `memanto ui` opens a local dashboard over everything the fleet has learned; browse it, search it, audit it.

**Every memory carries reference and origin.**
Confidence score, source, timestamp, and what it superseded. When an agent acts on something, you can trace where that belief came from and when it entered the fleet.

**Daily briefings on request.**
`memanto daily-summary` turns raw memory churn into a readable digest of what changed across your agents.

### Nothing to provision, nothing to rewrite

**One `pip install`.**
No vector DB, no embedding pipeline, no reranker, no schema migration, no backend to babysit. The retrieval engine ships in the box.

**Works with the agents you already run.**
`memanto connect claude-code` — same for Cursor, Codex, Windsurf, Cline, Continue, Goose, Copilot and more. One command per agent. No code changes, no wrapper SDK, no rewrite of your agent loop.

**Searchable the moment it's written.**
No LLM extraction at write time. No graph to rebuild. No indexing queue. `remember` returns and it's already retrievable — by every agent in the fleet.

### It stays yours

**Your fleet's memory is a file, not a hostage.**
`memanto memory export --okf` gives you plain Markdown — readable, diffable, committable. Switch stacks and take it with you. There's no lock-in because there's nothing to lock.

**Runs entirely on your own machine.**
Local Docker + Ollama, no account, no API key, nothing leaves your infrastructure. Or free cloud, or your own hosting — switch any time with one command.

**MIT licensed.** No open-core bait, no feature gate, no rug pull.

---

## Benchmarks

- **89.8% on LongMemEval** and **87.1% on LoCoMo** — outperforming Mem0, Zep, and Letta. [Public datasets →](https://huggingface.co/moorcheh)
- **Three primitives, not two**: `remember`, `recall`, and `answer`  LLM-grounded responses from memory, no extra API key.
- **Single-query retrieval.** No multi-stage pipelines, no graph schema, no rerankers.
- **Typed semantic memory.** 13 categories — `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship`, and more.

---


<p align="center">
  <a href="https://memanto.ai/discord">
    <img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord">
  </a>
  <a href="https://www.reddit.com/r/Memanto/">
    <img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Join Reddit">
  </a>
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
    <img src="https://img.shields.io/badge/Setup-Video-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Setup Video">
  </a>
  <a href="https://docs.memanto.ai">
    <img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Docs">
  </a>
</p>


---
## See it in action

<p align="center">
  <a href="https://youtu.be/zoKP4b_rUhY">
    <img src="https://img.youtube.com/vi/zoKP4b_rUhY/maxresdefault.jpg" alt="Watch Memanto in action" width="900">
  </a>
</p>

<p align="center">
  <em>▶ 
Retrieving memory for an AI agentic workflow is much more than a search — 6:20 min</em>
</p>


## Setup & Demo

<p align="center">
  <a href="https://www.youtube.com/watch?v=vEtOaoweIG4">
    <img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-demo.png" alt="Setup video">
  </a>
</p>

## Local Dashboard For Best UX

<p align="center">
  <a href="https://www.youtube.com/watch?v=5n976CmzohE">
    <img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-uidashboard.png" alt="Local dashboard demo">
  </a>
</p>

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

## CLI Reference

| Capability | Commands | What it does |
|---|---|---|
| System status dashboard | `memanto status` | View environment, configuration, server health, active session, and registered agents. |
| Local REST API + Web UI | `memanto serve`, `memanto ui` | Run the MEMANTO REST API locally and open an interactive browser UI. (Optional for CLI usage). |
| Agent lifecycle management | `memanto agent ...` | Create/list/delete agents, activate/deactivate sessions, and run `agent bootstrap` for an intelligence snapshot. |
| Memory capture at scale | `memanto remember` | Store single memories, batch-ingest from JSON, or `--from-conversation` to automatically extract facts from chat logs. |
| Single-memory editing & deletion | `memanto edit`, `memanto forget` | Update fields on an existing memory, or permanently delete a bad/outdated memory. |
| File upload to memory | `memanto upload` | Upload documents (.pdf, .docx, .xlsx, .json, .txt, .csv, .md) directly into an agent's memory namespace — content becomes instantly searchable via `recall`. |
| Advanced retrieval modes | `memanto recall` | Run standard search plus temporal queries (`--as-of`, `--changed-since`) with filters. |
| Grounded QA over memory | `memanto answer` | Generate RAG answers using retrieved memory context. |
| Daily intelligence workflows | `memanto daily-summary`, `memanto conflicts` | Generate summaries, detect contradictions, and resolve conflicts interactively. |
| Session and automation controls | `memanto session ...`, `memanto schedule ...` | Inspect sessions and enable scheduled daily summary runs. |
| Memory file pipelines | `memanto memory export`, `memanto memory sync` | Export structured memory markdown and sync `MEMORY.md` into projects. Add `--okf` to export/sync a portable [Open Knowledge Format](https://docs.memanto.ai/integrations/okf) bundle instead. |
| Import & migration | `memanto migrate` | Import memories from Mem0, Letta, or Supermemory - or an [OKF](https://docs.memanto.ai/integrations/okf) bundle into an agent. |
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
- **Discord**: [Join our Discord server](https://memanto.ai/discord)
- **Reddit**: [Join our Reddit community](https://www.reddit.com/r/Memanto/)
- **Email**: support@moorcheh.ai
- **X / Twitter**: [@moorcheh_ai](https://x.com/moorcheh_ai)

---

**MIT License**

<br>
<p align="center">
  <a href="README.md">English</a> | <a href="i18n/README_es.md">Español</a> | <a href="i18n/README_zh-CN.md">&#31616;&#20307;&#20013;&#25991;</a> | <a href="i18n/README_ja.md">&#26085;&#26412;&#35486;</a>
</p>
