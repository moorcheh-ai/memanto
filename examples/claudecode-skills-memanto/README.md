# Memanto + Claude Code Skills

> **Give your Claude Code skills a permanent engineering brain.**

`mattpocock/skills` gives you composable slash commands for real engineering — `/tdd`, `/grill-with-docs`, `/diagnose`, `/handoff`, and more. But each skill invocation starts cold. Your testing conventions, domain decisions, and architecture choices disappear when the terminal closes.

This integration layers **Memanto** on top of the skills ecosystem as a global, active memory companion. Every skill run can recall past decisions and store new ones — eliminating context re-prompting across sessions, terminals, and machines.

---

## The Problem: Context Fragmentation

```text
Session A  →  /grill-with-docs  →  "We use CQRS for the Order domain"
                                   "Cart ≠ Order — never mix the terms"
                                   ↓  terminal closes  ↓

Session B  →  /tdd              →  ??? No idea about CQRS or domain terms
                                   Agent re-asks the same questions
```

**Without Memanto:** every session starts from scratch. You repeat yourself constantly.  
**With Memanto:** decisions from Session A are automatically injected into Session B.

---

## Architecture

```text
┌─────────────────────────────────────────────┐
│            Claude Code session               │
│                                             │
│  /tdd-with-memory                           │
│    │                                        │
│    ├─1─ memanto-skills recall tdd ──────────┼──► Memanto
│    │         "past TDD decisions"           │      (semantic recall)
│    │              ↓                         │
│    │    [Inject context block]              │
│    │              ↓                         │
│    ├─2─ Run /tdd workflow                   │
│    │              ↓                         │
│    └─3─ memanto-skills store tdd "..." ─────┼──► Memanto
│              "new decision saved"           │      (persist)
│                                             │
└─────────────────────────────────────────────┘
         ↑ same pattern for every skill ↑
```

Three hooks in every skill run:

1. **Recall** — pull relevant engineering memories before the skill executes
2. **Execute** — run the skill with past context injected
3. **Store** — persist new decisions so future sessions inherit them

---

## Quick Start

### 1. Install

```bash
cd examples/claudecode-skills-memanto
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set MOORCHEH_API_KEY
# Get a free key at https://moorcheh.ai
```

### 3. Install the skills into Claude Code

```bash
# From your project root:
npx skills@latest add ./examples/claudecode-skills-memanto
```

### 4. Run the one-time setup

Open Claude Code and run:
```
/setup-memanto-skills
```

This injects a universal `## Memanto Memory` block into your `CLAUDE.md` — after that, **every skill** automatically recalls your engineering profile before running and prompts you to store insights after. No per-skill wrappers, no manual commands.

### 5. That's it

Use your skills normally — `/tdd`, `/grill-with-docs`, `/diagnose`, `/handoff`, any skill. The memory hook fires automatically for all of them.

```
/tdd          ← recalls your testing conventions automatically
/grill-with-docs  ← skips already-resolved questions automatically
/diagnose     ← recalls known failure modes automatically
/handoff      ← stores session insights automatically
```

### 6. Run the demo

```bash
# Store engineering decisions (Session 1)
python demo_session_1.py

# Open a new terminal — then recall them (Session 2)
python demo_session_2.py

# Or run the full pipeline in one shot
python demo_full.py

# Or launch the Streamlit UI
streamlit run app.py
```

---

## Skills Reference

### Universal hook (primary approach)

| Skill | Description |
|-------|-------------|
| `/setup-memanto-skills` | One-time setup — injects a `## Memanto Memory` block into `CLAUDE.md`/`AGENTS.md` that fires before and after **every skill automatically** |

After running `/setup-memanto-skills` once, no other configuration is needed. All existing and future skills (`/tdd`, `/grill-with-docs`, `/diagnose`, `/handoff`, any custom skill) get the memory hook for free.

### Standalone memory commands

| Skill | Description |
|-------|-------------|
| `/memanto-recall [skill\|hint]` | Manually inject your engineering profile before any session |
| `/memanto-store [insight]` | Manually persist a decision or insight |
| `/memanto-profile` | View your full accumulated engineering profile |

### Optional memory-enhanced skill variants

Pre-built wrappers for convenience — not required if you use `/setup-memanto-skills`.

| Skill | Wraps | What it adds |
|-------|-------|--------------|
| `/tdd-with-memory` | `/tdd` | Recalls test conventions; stores new framework/pattern decisions |
| `/grill-with-memory` | `/grill-with-docs` | Recalls past decisions; skips already-resolved questions; stores outcomes |
| `/diagnose-with-memory` | `/diagnose` | Recalls known failure modes; stores root-cause learnings |
| `/handoff-with-memory` | `/handoff` | Writes handoff doc AND stores session insights to Memanto |

---

## CLI Reference

```bash
# Recall context for a skill (prints a ready-to-inject markdown block)
memanto-skills recall tdd --hint "writing tests for auth module"
memanto-skills recall grill-with-docs --types decision,instruction

# Store a single insight
memanto-skills store tdd "Always use pytest-asyncio for async tests" --type instruction
memanto-skills store grill-with-docs "CQRS in Order domain" --type decision

# Store from a file (e.g. a session summary)
memanto-skills store-file grill-with-docs ./session-notes.txt --split

# View your full engineering profile
memanto-skills profile
memanto-skills profile --types decision,instruction

# Deactivate session
memanto-skills clear-agent
```

---

## Memory Types

| Type | Meaning | Example |
|------|---------|---------|
| `instruction` | Hard rule — always/never | "Always use pytest-asyncio for async tests" |
| `decision` | Architectural choice made | "CQRS for the Order domain" |
| `preference` | Style / tool preference | "Prefer explicit imports over star imports" |
| `fact` | Fixed truth about the codebase | "The Order module owns cart finalization" |
| `learning` | Discovered knowledge | "Redis TTL flush causes test flakiness" |
| `artifact` | A created file or spec | "PRD for checkout redesign: issue #42" |
| `goal` | An active objective | "Migrate auth to OAuth2 by Q3" |
| `error` | A known bug pattern | "Double-spend race condition in payment flow" |
| `context` | Background information | "Monorepo: frontend in /web, API in /api" |

---

## Workflow Example

```text
Session A (Monday)
──────────────────
/grill-with-docs  →  "Should we use CQRS?"  →  "Yes, for Order domain"
                  →  stores: decision: "CQRS for Order domain"

/tdd              →  writes tests for CheckoutService
                  →  stores: instruction: "Use InMemoryRepository at test seams"
                  →  stores: decision: "Test through public interface only"


Session B (Tuesday — fresh terminal)
─────────────────────────────────────
/grill-with-memory         ← runs recall first
  → injected context:
    [decision] CQRS for Order domain
    [instruction] Use InMemoryRepository at test seams
  → "You previously decided X — does this plan conflict with that?"
  → NO re-asking of already-resolved questions ✅

/tdd-with-memory           ← runs recall first
  → injected context:
    [instruction] Use InMemoryRepository at test seams
    [instruction] Always use pytest-asyncio for async tests
  → zero repeated instructions ✅
```

---

## Python API

```python
from memanto_skills import MemantoSkillsClient

client = MemantoSkillsClient()  # reads MOORCHEH_API_KEY from env
client.setup()

# Before a skill: inject engineering context
profile = client.recall_for_skill(
    skill_name="tdd",
    task_hint="writing tests for the checkout module",
)
print(profile.format_context_block())   # inject into Claude's context

# After a skill: persist new decisions
client.store_from_skill(
    skill_name="tdd",
    summary="Always use InMemoryRepository at test seams, never mock the DB directly",
    memory_type="instruction",
    confidence=0.95,
)

# Batch store multiple insights
client.batch_store_from_skill("grill-with-docs", [
    {"summary": "CQRS for Order domain", "memory_type": "decision"},
    {"summary": "Cart ≠ Order", "memory_type": "instruction"},
])

client.teardown()
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MOORCHEH_API_KEY` | ✅ | — | Your Moorcheh API key |
| `MEMANTO_AGENT_ID` | ❌ | `skills-dev-profile` | Agent ID (memory namespace) |
| `MEMANTO_RECALL_LIMIT` | ❌ | `8` | Max memories injected per skill |

---

## Project Structure

```text
examples/claudecode-skills-memanto/
├── .claude-plugin/
│   └── plugin.json              # Claude Code plugin manifest
├── skills/
│   ├── memanto-recall/          # Inject profile before any session
│   ├── memanto-store/           # Persist insight after any session
│   ├── memanto-profile/         # View full engineering profile
│   ├── tdd-with-memory/         # /tdd + recall + store
│   ├── grill-with-memory/       # /grill-with-docs + recall + store
│   ├── diagnose-with-memory/    # /diagnose + recall + store
│   └── handoff-with-memory/     # /handoff + recall + store
├── memanto_skills/
│   ├── __init__.py              # Public API
│   ├── client.py                # MemantoSkillsClient — core integration
│   ├── profile.py               # MemoryProfile — recalled context container
│   ├── extractor.py             # Insight extractor + memory-type inference
│   ├── utils.py                 # Context block formatter
│   └── cli.py                   # memanto-skills CLI
├── demo_session_1.py            # Store phase demo
├── demo_session_2.py            # Cross-session recall demo (run in new terminal)
├── demo_full.py                 # Full pipeline demo
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## Social

- X post: [add link after publishing]
- Reddit post: [add link after publishing]
