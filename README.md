<p align="center">
  <a href="https://www.memanto.ai/">
    <img alt="Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="440">
  </a>
</p>

<h3 align="center">Memory that AI Agents Love!</h3>

<p align="center">
  Memanto is a <strong>Memory Agent</strong>; a companion agent that manages the memories of your other agents:<br>
  what to keep, what conflicts, what expires, and who needs to know.
</p>

<p align="center">
  <a href="https://github.com/moorcheh-ai/memanto"><img alt="GitHub stars" src="https://img.shields.io/github/stars/moorcheh-ai/memanto?style=social"></a>
  <a href="https://pepy.tech/projects/memanto"><img alt="Downloads" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
  <a href="https://arxiv.org/abs/2604.22085"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2604.22085-b31b1b.svg"></a>
  <a href="https://pypi.org/project/memanto/"><img alt="PyPI" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
</p>

```bash
pip install memanto
```

<!-- ============================================================
     DEMO GIF — highest-impact missing asset. assets/demo.gif
     VHS tape provided separately. Under 15s, under 3MB.
     ============================================================ -->

<p align="center">
  <img alt="Memanto in 15 seconds" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/demo.gif" width="900">
</p>

---

> **Every platform will store your agents' memory. None of them will manage it.** Managing it across platforms is against their interest. That is the job of a Memory Agent.

Persistence is solved. Claude, Bedrock, Cursor, and every vector store will happily keep what your agents write. None of them will tell you that two of your agents now believe opposite things about your auth service, that a preference from March has quietly outranked a decision from last week, or that the agent you spun up this morning is about to redo work another one finished and reverted.

Storage is a filing cabinet. Memanto is the chief of staff; it decides what goes in, watches the access, resolves what contradicts, discards what's stale, and briefs each agent before it acts.

---

## It's an agent, not an API

Memanto isn't a library you call. It's a second agent that runs beside your fleet and does six things on its own judgment. Each one is a real behavior with a command behind it, nothing here is a roadmap item.

| | What Memanto does | Run it |
|---|---|---|
| **Observes & extracts** | Watches the interaction streams of the agents it serves and pulls durable knowledge out of ephemeral traffic — decisions, preferences, facts, failures — instead of archiving transcripts wholesale. | `memanto remember --from-conversation` |
| **Consolidates** | Merges extracted memories into one canonical estate. Duplicates collapse, fragments join, repeated observations strengthen confidence instead of multiplying rows. | `memanto schedule enable` |
| **Reconciles** | When new knowledge contradicts old, Memanto supersedes rather than appends — preserving what was believed and when. "What's true now" and "what did we believe then" stay different questions. | `memanto conflicts` |
| **Forgets** | Decay, expiry, and deliberate deletion are policies it executes, not cleanup you remember to do. An estate that only grows becomes noise; managed forgetting is what keeps recall sharp at month twelve. | `memanto forget` |
| **Briefs** | Before an agent acts, Memanto hands it the minimal relevant slice of the estate. Your agents don't query anything — they get briefed by a colleague. | `memanto agent bootstrap` |
| **Moves knowledge** | Through the Open Knowledge Format, the estate crosses frameworks and vendors — so a fleet spanning Claude Code, Cursor, and your own stack shares one memory instead of five silos. | `memanto memory export --okf` |

**And it does this while you're asleep.** `memanto schedule enable` and the loop runs daily: new memories curated, duplicates merged across agents, contradictions flagged for your review. You come back to a fleet that knows more than it did yesterday, without having sorted anything yourself.

---

## 60 seconds to a managed fleet

```bash
pip install memanto
memanto                            # "On-Prem" (Docker, no account) or "Cloud" (free key)
memanto connect claude-code        # also: cursor, codex, windsurf, cline, goose, copilot…
```

Your agents now share one managed estate. No code changes, no wrapper, no rewrite of your agent loop.

```bash
# backend-agent learns something on Monday
memanto remember "Auth migrated to JWT — session cookies deprecated" --type decision

# review-agent, which never saw that session, knows it on Friday
memanto recall "how does auth work"
memanto answer  "why did we drop session cookies?"     # grounded, no extra API key

# what did the fleet believe last Tuesday? what changed since the release?
memanto recall "deployment policy" --as-of 2026-08-05
memanto recall "deployment policy" --changed-since v2.1
```

macOS, Linux, Windows. `memanto ui` opens a local dashboard over the whole estate — browse it, search it, audit it.

---

## Own your agentic memory

This is the part that matters in two years, and it's the part every platform-native memory feature is designed to prevent.

**Your estate is a file.** `memanto memory export --okf` gives you the [Open Knowledge Format](https://docs.memanto.ai/integrations/okf) — plain Markdown, readable, diffable, committable, greppable. Not a proprietary dump you can technically request. The actual working format.

**It moves.** `memanto migrate` imports from Mem0, Letta, Supermemory, or any OKF bundle. The same command works in reverse. OKF is an open interchange format any framework or vendor can implement — including ours' competitors, deliberately.

**It runs on your machine.** Local Docker + Ollama, no account, no API key, nothing leaves your infrastructure. Or free cloud, or your own hosting. `memanto config backend` switches between them in one command, and the estate comes with you.

**MIT.** No open-core tier waiting to gate the useful half. No feature flags, no seat limits, no rug pull.

There is no lock-in because there is nothing to lock.

---

## Security & sovereignty

<!-- ============================================================
     TODO — Majid: fill from your hardening work. Structure is
     right; the specifics are yours. Items marked ⟨…⟩ need input.
     Anything you can't substantiate today, delete rather than soften.
     ============================================================ -->

**Nothing leaves your machine in on-prem mode.** Docker + Ollama, no account, no outbound calls. The full loop — extraction, consolidation, reconciliation, briefing — runs locally.

**Scoped by default.** Each agent gets its own namespace. Your production-ops agent doesn't read your scratch experiments; you provision exactly what each one should know and nothing more.

**Every belief is traceable.** Confidence score, source, timestamp, and what it superseded. When an agent acts on something, you can walk back to where that belief entered the fleet and when — which is the difference between an auditable estate and a black box.

---

## Unlike memory storage

| | Memory storage | **Memanto** |
|---|---|---|
| What it is | A database with an SDK — write, embed, retrieve | An agent with judgment over your fleet's memory |
| Core behavior | Persist | Curate, reconcile, consolidate, forget, brief |
| Who decides what's kept | You, in application code | Memanto, on policy you set once |
| When two agents disagree | Last write wins, silently | Both versioned, surfaced for review |
| Forgetting | A `DELETE` you remember to run | A first-class policy that runs on schedule |
| Scope | One app, one stack, one vendor's walls | A fleet, across stacks and vendors |
| Your data | Exportable in theory | The working format *is* portable Markdown |

Storage substrates sit *beneath* Memanto — vector stores, filesystems, and platform-native memory features are all backends it manages. Their commoditization is good for you: it makes the substrate free and leaves the management to something that's actually good at it.

---

<p align="center">
  <strong>⭐ Star the repo if Memanto is managing your fleet's memory</strong><br>
  <sub>It's the signal that tells us to keep building this in the open, under MIT, with nothing held back.</sub>
</p>

---

## Developer experience

**One `pip install`.** No vector store to provision, no embedding pipeline, no reranker, no schema migration, no backend to babysit. The retrieval engine ships in the box.

**Works with what you already run.** `memanto connect claude-code` — same for Cursor, Codex, Windsurf, Cline, Continue, Goose, Copilot, and more. One command each.

**Searchable the moment it's written.** No extraction pass at write time, no graph to rebuild, no indexing queue. `remember` returns and every agent in the fleet can already recall it.

**Typed, not soup.** 13 memory categories — `instruction`, `fact`, `decision`, `goal`, `preference`, `relationship`, and more — so recall is filterable instead of one undifferentiated blob.

**A dashboard, not a log file.** `memanto ui` for the whole estate. `memanto daily-summary` for a readable digest of what changed across your agents. `memanto status` for registered agents, sessions, and health.

---

<details>
<summary><strong>Full CLI reference</strong></summary>

<br>

| Capability | Commands | What it does |
|---|---|---|
| System status | `memanto status` | Environment, configuration, server health, active session, registered agents. |
| Local REST API + web UI | `memanto serve`, `memanto ui` | Run the REST API locally and open an interactive browser UI. |
| Agent lifecycle | `memanto agent ...` | Create/list/delete agents, activate sessions, run `agent bootstrap`. |
| Memory capture at scale | `memanto remember` | Single memories, batch JSON, or `--from-conversation` to extract from chat logs. |
| Editing & deletion | `memanto edit`, `memanto forget` | Update fields on a memory, or permanently delete a bad one. |
| File ingestion | `memanto upload` | Bring .pdf, .docx, .xlsx, .json, .txt, .csv, .md into an agent's namespace. |
| Advanced recall | `memanto recall` | Standard search plus temporal queries (`--as-of`, `--changed-since`) with filters. |
| Grounded answers | `memanto answer` | Generate answers from retrieved memory context. |
| Daily intelligence | `memanto daily-summary`, `memanto conflicts` | Summaries, contradiction detection, interactive resolution. |
| Sessions & automation | `memanto session ...`, `memanto schedule ...` | Inspect sessions, enable scheduled daily runs. |
| Estate export & sync | `memanto memory export`, `memanto memory sync` | Export structured Markdown, sync `MEMORY.md` into projects. `--okf` for a portable [OKF](https://docs.memanto.ai/integrations/okf) bundle. |
| Import & migration | `memanto migrate` | Import from Mem0, Letta, Supermemory, or an OKF bundle. |
| Configuration | `memanto config show` | API key status, active agent/session, server settings, schedule time. |
| Fleet integration | `memanto connect ...` | Claude Code, Codex, Cursor, Windsurf, Antigravity, Gemini CLI, Cline, Continue, OpenCode, Goose, Roo, GitHub Copilot, Augment. |

**Memory types:** `instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

```bash
memanto remember "User prefers concise answers" --type preference
memanto recall "user communication style" --type preference
```

Complete reference: [CLI User Guide](https://docs.memanto.ai/cli)

</details>

<details>
<summary><strong>Install options — fully local vs. free cloud</strong></summary>

<br>

**Fully local. No account, no API key, nothing leaves your machine:**

```bash
pip install memanto
memanto           # choose "On-Prem" — guides through Docker + Ollama setup
```

Requires Docker.

**Free cloud. No card, ~60 seconds:**

```bash
pip install memanto
memanto           # choose "Cloud" — paste your free API key
```

Free key at [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys) — 100K free operations.

Switch any time: `memanto config backend`

</details>

<details>
<summary><strong>Architecture</strong></summary>

<br>

Recall is powered by an information-theoretic semantic engine that ships in the box — as a local Docker container or as a free cloud service. The `memanto` CLI manages either for you. Storage substrates beneath it are pluggable; Memanto is the agent above them.

<p align="center">
  <img alt="Architecture" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="900">
</p>

**On-prem:**

<p align="center">
  <img alt="On-prem architecture" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="900">
</p>

</details>

<details>
<summary><strong>SDKs & REST API</strong></summary>

<br>

**TypeScript / Node.js** — [`@moorcheh-ai/memanto`](sdks/typescript) boots a local Memanto server via `uvx` and exposes an ergonomic client (`remember` / `recall` / `answer`).

**REST API** — start with `memanto serve`. Endpoint reference at [docs.memanto.ai/api](https://docs.memanto.ai/api) and `http://localhost:8000/docs` while running.

</details>

---

## Watch it work

| | |
|---|---|
| [**Recall is more than search**](https://youtu.be/zoKP4b_rUhY) — 6:20 | [**Setup & demo**](https://www.youtube.com/watch?v=vEtOaoweIG4) |
| [**Local dashboard tour**](https://www.youtube.com/watch?v=5n976CmzohE) | [**Docs →**](https://docs.memanto.ai) |

---

## Research

**[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://arxiv.org/abs/2604.22085)**

On public recall benchmarks we report 89.8% on LongMemEval and 87.1% on LoCoMo. <!-- TODO: state reader model, judge model, and subset here — you should be the one in this space whose conditions are legible. --> Datasets and harness are open at [huggingface.co/moorcheh](https://huggingface.co/moorcheh) — run them yourself.

A caveat we'd rather say out loud: cross-project scores on these benchmarks are not comparable. Reader model, judge model, judge prompt, and retrieval budget each move results by several points, and no two published runs share a configuration. Treat every number in this category — including ours — as directional. What a Memory Agent should eventually be measured on isn't recall at all, but estate quality over time: contradiction rate, staleness, and precision at month six.

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

## Community

<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Reddit"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Docs"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/27378"><img src="https://trendshift.io/api/badge/repositories/27378" alt="Trendshift" width="220"></a>
  <a href="https://mcptoplist.com/server/glama%2Fmoorcheh-ai%2Fmemanto"><img src="https://mcptoplist.com/badge/glama%2Fmoorcheh-ai%2Fmemanto.svg" alt="MCP Top List" width="220"></a>
  <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
</p>

Questions: [support@moorcheh.ai](mailto:support@moorcheh.ai) · [@moorcheh_ai](https://x.com/moorcheh_ai)

---

<p align="center">
  <strong>MIT License</strong><br>
  <sub><a href="README.md">English</a> · <a href="i18n/README_es.md">Español</a> · <a href="i18n/README_zh-CN.md">简体中文</a> · <a href="i18n/README_ja.md">日本語</a></sub>
</p>
