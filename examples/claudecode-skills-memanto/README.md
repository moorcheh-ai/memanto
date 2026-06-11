# Claude Code Skills × Memanto — Cross-Session Engineering Memory

> Your AI coding agent finally remembers your architecture. `/grill-with-docs`
> decides "Cart ≠ Order, use CQRS" in one terminal — and `/tdd` honours it in
> the next, in a fresh session, with **zero repeated instructions**.

This example makes [Memanto](https://memanto.ai) a **global, active memory
companion** across [`mattpocock/skills`](https://github.com/mattpocock/skills)
executions. It solves the *context fragmentation* problem: skills like `/tdd`,
`/diagnose`, `/grill-with-docs`, and `/handoff` each run cold, so architectural
choices, codebase quirks, and coding preferences vanish when a session ends.

Closes [#508](https://github.com/moorcheh-ai/memanto/issues/508).

---

## How it works — three real lifecycle hooks

Memory is wired into the **Claude Code hook lifecycle**, not bolted onto forked
skills. The hooks fire on the *real, unmodified* mattpocock skills — nothing to
remember to invoke, nothing to copy-paste.

![How it works](./assets/how-it-works-three-real-lifecycle-hooks.png)

### Component architecture

![Component architecture](./assets/component-architecture.png)

### Mapping to the bounty's implementation guidelines

| Guideline | Where | What it does |
|---|---|---|
| **Global Memory Hook** | `install.py` → `.claude/settings.json` | Registers `SessionStart`, `UserPromptSubmit`, `Stop` against the Memanto-backed scripts in `hooks/`. One command, idempotent, backs up your settings, and preserves any hooks you already had — even inside shared entries. |
| **Active Extraction** | `hooks/on_stop.py` → `SkillMemory.distill_and_store` | Hands the session summary to **Memanto's backend LLM** (`answer()`), which distills durable decisions/rules/preferences into Memanto's typed memory categories and persists them. Guards against `stop_hook_active` re-fires so a session is never distilled twice. |
| **Dynamic Injection** | `hooks/on_prompt.py` → `SkillMemory.recall_for_skill` | Detects the invoked skill (path-safe: `/usr/local/bin` is not a skill), recalls the memories most relevant to it, and injects them as a concise `<engineering-profile>` system-constraint block. |

> **LLM-powered, not regex.** Extraction leads with Memanto's backend LLM (the
> bounty's "backend LLM access to actively listen"), and falls back to a
> conservative heuristic only if the LLM path is unavailable — so a hook never
> silently no-ops.

---

## Quick start

```bash
cd examples/claudecode-skills-memanto
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"                  # installs package + dev tools (pytest, ruff, mypy)

cp .env.example .env                     # then add your key, or just export it:
export MOORCHEH_API_KEY=mch_xxxxxxxxxxxx # https://console.moorcheh.ai/api-keys

python install.py                        # register the hooks in ./.claude/settings.json
# (use --global to install into ~/.claude/settings.json for every project)
```

That's it. Now use the real mattpocock skills as you always do — `/tdd`,
`/grill-with-docs`, `/diagnose`, `/handoff`. Memory accrues and replays
automatically.

Verify the setup at any time:

```bash
memanto-skills doctor
```

---

## See it work (no Claude Code required)

Three scripts prove cross-session, cross-skill persistence across **completely
separate processes** with no shared in-memory state:

| Script | Simulates | Proves |
|---|---|---|
| `demo_session_1.py` | `/grill-with-docs` architecture session | Active extraction: LLM distills 4 decisions into Memanto |
| `demo_session_2.py` | Fresh `/tdd` session on same codebase | Dynamic injection: all 4 decisions recalled, zero re-prompting |
| `demo_session_3.py` | `/handoff` + fresh `/grill-with-docs` | Multi-skill accrual: profile grows across unrelated skills |

```bash
python demo_session_1.py   # /grill-with-docs → CQRS, Cart≠Order, Postgres+Redis, Money VO
python demo_session_2.py   # fresh /tdd → recalls all 4 decisions, zero re-prompting
python demo_session_3.py   # /handoff → TypeScript migration, Result<T,E>, domain isolation
                           # then /grill-with-docs sees ALL memories from all sessions
```

`demo_session_2.py` prints the exact context block the `UserPromptSubmit` hook
injects before `/tdd` runs:

```text
<engineering-profile source="memanto" skill="tdd">
Relevant engineering memory for /tdd (carried over from previous skill
sessions — honour it, do not re-ask the user):

Rules (always honour):
  - Cart and Order are distinct domain concepts. A Cart is mutable and
    pre-purchase; an Order is immutable once placed. …
  - Money values must always be represented using a Money value object. …

Decisions made:
  - The Orders service uses CQRS: commands and queries are strictly separated…
  - The Orders service write side is backed by Postgres; the read-model cache
    is backed by Redis.
</engineering-profile>
```

---

## Manual control — the `memanto-skills` CLI

The hooks are automatic; the CLI (and the `/memanto-companion` skill) is the
manual surface.

```bash
memanto-skills profile                       # show the accumulated engineering profile
memanto-skills recall tdd --hint "auth flow" # preview what /tdd would receive
memanto-skills store tdd "We standardised on Vitest + AAA structure."
memanto-skills install [--global]            # (re)install hooks
memanto-skills uninstall [--global]          # remove hooks (yours stay untouched)
memanto-skills doctor                        # config + connectivity + skill routes
```

---

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `MOORCHEH_API_KEY` | *(required)* | Your Moorcheh key. Free tier: 100K ops/month. |
| `MEMANTO_AGENT_ID` | `skills-dev-profile` | The shared memory namespace. Use a stable per-developer or per-project id. |
| `MEMANTO_RECALL_LIMIT` | `8` | How many memories to inject before a skill. |
| `MEMANTO_MIN_SIMILARITY` | *(unset — no floor)* | Optional floor on Memanto's ITS retrieval score. Leave unset: ITS scores live on a small, non-cosine scale (top hits ≈ 0.1–0.2), and Memanto already returns relevant results only. |

---

## Repository layout

```text
claudecode-skills-memanto/
├── install.py                  # one-command, idempotent hook installer (+ --uninstall)
├── .claude-plugin/plugin.json  # Claude Code plugin manifest (ships /memanto-companion)
├── memanto_skills/             # the installable package
│   ├── client.py               #   SkillMemory: setup / recall_for_skill / distill_and_store
│   ├── extractor.py            #   backend-LLM distillation (+ heuristic fallback)
│   ├── profile.py              #   MemoryProfile -> injectable <engineering-profile> block
│   ├── skill_map.py            #   per-skill recall routing
│   ├── config.py               #   env-driven config
│   ├── installer.py            #   settings.json patching (preserves your hooks)
│   └── cli.py                  #   `memanto-skills`
├── hooks/                      # the three lifecycle hook entry points
│   ├── session_start.py        #   SessionStart  -> profile briefing
│   ├── on_prompt.py            #   UserPromptSubmit -> recall + inject
│   ├── on_stop.py              #   Stop (async) -> distill + store
│   └── _common.py              #   exit-0 contract, skill detection, transcript reading
├── skills/memanto-companion/   # SKILL.md for manual inspect/recall/store
├── demo_session_1.py           # /grill-with-docs → stores 4 architectural decisions
├── demo_session_2.py           # fresh /tdd → recalls them all, zero re-prompting
├── demo_session_3.py           # /handoff → adds more; /grill-with-docs sees all of it
└── tests/                      # 56 unit tests, fully mocked (no network, no key)
```

### Design principles

- **Zero-overhead & fail-safe.** Hooks never block the editor. The exit-0
  contract is enforced in exactly one place (`hooks/_common.py:run`), so any
  internal failure — no key, network down, malformed transcript — degrades
  silently instead of surfacing editor errors.
- **One network call per hook.** Session activation is attempted first and
  agent creation only happens on the first ever run, keeping the prompt-path
  latency minimal.
- **Skill-aware recall.** `/tdd` pulls testing conventions; `/grill-with-docs`
  pulls architecture and domain terminology — see `skill_map.py`. Unknown or
  custom skills fall back to a generic engineering-profile route.
- **Typed memory, sourced from the SDK.** Memory types and input limits are
  imported from the `memanto` package itself, so this example can never drift
  from the platform's schema.
- **Respectful install.** Re-running `install.py` replaces only our own hook
  commands (matched by path), preserves your hooks even when they share an
  entry with ours, and backs up your settings before any write.

---

## Run the tests

```bash
pytest          # 56 tests, mocked SDK — no API key needed
ruff check .
```

---

## Built on

- [Memanto](https://github.com/moorcheh-ai/memanto) — typed semantic memory with
  information-theoretic retrieval (`remember` / `recall` / `answer`).
- [mattpocock/skills](https://github.com/mattpocock/skills) — sharp,
  single-purpose Claude Code skills.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks) — the lifecycle
  events this layer plugs into.

MIT licensed.
