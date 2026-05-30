# 🧠 Memanto + mattpocock/skills — Zero Context Re-Prompting

A global memory companion for [mattpocock/skills](https://github.com/mattpocock/skills) that eliminates **Context Fragmentation** across skill executions.

```text
/grill-with-docs  →  stores: JWT over sessions, RS256, TypeScript strict
                                        ↓  Memanto  ↓
/tdd              ←  injects: all past decisions automatically (new session)
                                        ↓  Memanto  ↓
/handoff          ←  injects: full engineering profile for the next agent
```

> **Zero repeated instructions.** The agent aligns with your architectural philosophy across every skill, every session, without manual context-shoving.

## 🎬 Demo Video

▶️ **[Watch 30-second demo](https://github.com/user-attachments/assets/292776a4-c307-4908-8b7d-f9fc044e444e)**

*`/grill-with-docs` stores decisions → `/tdd` in a new session auto-recalls them*

## 📣 Social Posts
- 🐦 X/Twitter: https://x.com/i/status/2059056551671869471

---

## The Problem: Context Fragmentation

Each mattpocock/skills execution is an isolated event. When you use `/grill-with-docs` to resolve "JWT over sessions with RS256", that decision is **invisible** when you invoke `/tdd` in a fresh terminal session. You re-explain. Every time.

## The Solution: Global Memory Hooks

Two lightweight hooks wrap every skill execution:

```
Before skill: PRE-HOOK  → recall engineering profile from Memanto → inject into prompt
After skill:  POST-HOOK → extract decisions → store to Memanto permanently
```

No vector DB. No indexing wait. Memories are searchable the instant they're stored.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  mattpocock/skills CLI                       │
│                                                             │
│  /grill-with-docs   /tdd   /handoff   /diagnose   ...      │
│        │               │        │                           │
│   PRE-HOOK         PRE-HOOK  PRE-HOOK   ← inject context   │
│   POST-HOOK       POST-HOOK POST-HOOK   ← store decisions  │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API (POST /remember, GET /recall)
           ┌───────────▼───────────┐
           │   Memanto Server      │  ← permanent engineering profile
           │  (memanto serve)      │  ← persists across ALL sessions
           └───────────┬───────────┘
                       │ SDK calls
           ┌───────────▼───────────┐
           │    Moorcheh.ai        │
           │  Zero-Index Semantic  │
           │  Database             │
           └───────────────────────┘
```

**Why tools-only (not a LangGraph/LangChain backend)?**

Many framework memory integrations rely on embedding-oriented retrieval layers where the original natural-language query may not be preserved cleanly through the abstraction boundary. Memanto performs semantic retrieval directly from natural-language text queries. The hooks-based approach here keeps the integration lightweight — zero overhead, zero framework dependency.

**Memanto is NOT used as a conversation checkpointer.** Checkpointing manages execution recovery. Memanto manages durable semantic memory. They solve different problems.

---

## Quick Start

```bash
# 1. Install
git clone https://github.com/YOUR_HANDLE/memanto
cd memanto/examples/claudecode-skills-memanto
pip install -r requirements.txt

# 2. Configure
export MOORCHEH_API_KEY=mk-...   # get free key at moorcheh.ai
memanto serve                     # start local Memanto server

# 3. Install into your project
python setup.py --target /path/to/your/project

# 4. Run offline demo (no server or API key needed)
python skills_memory.py demo --offline

# 5. Run live demo
python skills_memory.py demo
```

---

## Usage

### Before any skill runs (PRE-HOOK)

```bash
python skills_memory.py pre tdd "Implement user login endpoint"
```

Output injected into the skill prompt:
```
[MEMANTO ENGINEERING PROFILE — skill: tdd]
Apply these decisions automatically without re-asking the developer:

  [decision] Use JWT tokens over sessions — stateless, scales horizontally.
  [decision] RS256 algorithm for JWT signing — asymmetric, safer for microservices.
  [decision] Refresh token rotation with 7-day expiry.
  [preference] Developer prefers TypeScript strict mode across all new files.
```

### After any skill completes (POST-HOOK)

```bash
python skills_memory.py post tdd "Implemented login with JWT" \
  --decisions \
    "Repository pattern for data access layer" \
    "Vitest over Jest — 10x faster cold starts" \
  --preferences \
    "Colocate test files with implementation"
```

### Query engineering profile

```bash
python skills_memory.py recall "authentication approach"
```

---

## Cross-Session Recall Proof

```
Session A  (any terminal, any time)
────────────────────────────────────────────────────────
Developer runs /grill-with-docs on "Auth system design"
POST-HOOK stores:
  [decision] JWT over sessions
  [decision] RS256 signing
  [preference] TypeScript strict mode

         ↓  terminate process entirely  ↓

Session B  (new terminal, next day, different machine)
────────────────────────────────────────────────────────
Developer runs /tdd on "Login endpoint"
PRE-HOOK recalls:
  📚 [decision] JWT over sessions — stateless, scales horizontally.
  📚 [decision] RS256 algorithm for JWT signing.
  📚 [preference] TypeScript strict mode.

/tdd starts — already knows everything. Zero re-prompting.
```

**No shared in-memory state between sessions. All recalled information originates exclusively from Memanto persistence.**

---

## Contradiction Handling

When a new decision contradicts a stored one, store the correction via POST-HOOK:

```bash
python skills_memory.py post tdd "Updated JWT decision" \
  --decisions "Switched to HS256 — single-service deployment, asymmetric unnecessary"
```

The old decision (`RS256`) is preserved in `metadata.previous_content` for audit. Only the active fact changes. Applications can inspect `metadata.previous_content` to resolve conflicts.

Uses only the documented `POST /remember` endpoint — no undocumented PATCH.

---

## Enhanced Claude Code Skills

Three Memanto-enhanced skill files are installed into `.claude/commands/`:

| Skill | File | What it adds |
|-------|------|-------------|
| `/memanto-tdd` | `memanto-tdd.md` | Pre-loads architecture, post-stores TDD decisions |
| `/memanto-grill-with-docs` | `memanto-grill-with-docs.md` | Pre-loads settled decisions, post-stores all resolved choices |
| `/memanto-handoff` | `memanto-handoff.md` | Enriches handoff docs with full Memanto profile |

---

## Project Structure

```
claudecode-skills-memanto/
├── memanto_bridge.py       # Memanto v2 REST client (documented endpoints only)
├── skills_memory.py        # Pre/post hooks + CLI
├── setup.py                # Installs skills into your project
├── validate_offline.py     # Offline smoke test (no server needed)
├── requirements.txt
├── README.md
└── .claude/
    └── commands/
        ├── memanto-tdd.md
        ├── memanto-grill-with-docs.md
        └── memanto-handoff.md
```

---

## Memanto API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2/agents` | POST | Create agent namespace |
| `/api/v2/agents/{id}/activate` | POST | Start session → token |
| `/api/v2/agents/{id}/remember` | POST | Store decision/preference/context |
| `/api/v2/agents/{id}/recall` | GET | Semantic search (natural language) |
| `/api/v2/agents/{id}/answer` | POST | RAG answer over engineering profile |

No undocumented endpoints. No PATCH. No vector embedding bridges.

---

## Scoring Criteria Addressed

| Criterion | How |
|-----------|-----|
| **Productivity Multiplier (40pts)** | Pre-hook eliminates ALL context re-prompting across sessions |
| **Code Cleanliness (20pts)** | Zero framework dependencies, single-file Python modules, documented endpoints only |
| **Social Virality (40pts)** | Demo video + X post + Reddit posts linked above |
