# Hermes + Memanto: Persistent Memory Agent

This package adds [Memanto](https://memanto.ai) as a **memory agent** for the
[Hermes agent](https://github.com/NousResearch/hermes-agent). Memanto gives
Hermes typed long-term memory with confidence and provenance, semantic recall,
and RAG-style answers, backed by the [Moorcheh](https://moorcheh.ai) vector
platform.

Unlike a passive "memory layer", every namespace in Memanto is a first-class
**agent** (`memanto agent create/activate`), so this provider maps one Hermes
identity to one Memanto agent.

## What you get

- **Auto-recall** — relevant memories are injected before each turn.
- **Turn capture** — conversation turns are stored as `event` memories.
- **Explicit tools** — `memanto_remember`, `memanto_recall`, `memanto_answer`.
- **Memory mirroring** — Hermes' built-in `memory` writes are echoed into Memanto.
- **Profile isolation** — `agent_id: hermes-{identity}` scopes memory per Hermes profile.

## Why a standalone plugin?

Hermes' built-in providers under `plugins/memory/` are a closed set; new memory
backends ship as standalone plugins that users install into
`~/.hermes/plugins/`. Hermes discovers a memory provider as a **directory**
under `$HERMES_HOME/plugins/<name>/` containing an `__init__.py` that exposes
`register(ctx)` plus a `plugin.yaml`. This package ships exactly that, plus an
installer that drops it into place.

## Prerequisites

- Python 3.10+
- A running [Hermes agent](https://github.com/NousResearch/hermes-agent) install
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)

## Install

```bash
# 1. Install this package (pulls in the memanto SDK)
pip install hermes-memanto

# 2. Drop the plugin into your Hermes home (~/.hermes/plugins/memanto/)
hermes-memanto-install

# 3. Configure your key + select the provider
export MOORCHEH_API_KEY=...          # https://console.moorcheh.ai/api-keys
hermes config set memory.provider memanto
```

`hermes memory setup` will also list **memanto** once the plugin is installed,
and writes `MOORCHEH_API_KEY` into `~/.hermes/.env` for you.

### From a source checkout

```bash
git clone https://github.com/moorcheh-ai/memanto.git
cd memanto/integrations/hermes-agents
pip install -e .
hermes-memanto-install            # or: hermes-memanto-install --hermes-home /path/to/.hermes
```

The installer copies `hermes_memanto/provider.py` verbatim as the plugin's
`__init__.py`, so the installed plugin is self-contained and only needs the
`memanto` SDK at runtime (declared in its `plugin.yaml`).

## Configuration

After install, settings live in `$HERMES_HOME/memanto.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `agent_id` | `hermes-{identity}` | Memanto agent id (memory namespace). `{identity}` expands to the Hermes profile name. |
| `pattern` | `tool` | Agent pattern used when auto-creating: `support`, `project`, or `tool`. |
| `auto_recall` | `true` | Inject relevant memories before each turn. |
| `auto_capture` | `true` | Store cleaned conversation turns as `event` memories. |
| `auto_create` | `true` | Create the agent on first use if it does not exist. |
| `mirror_memory_writes` | `true` | Echo Hermes' built-in `memory` writes into Memanto. |
| `max_recall_results` | `10` | Max memories formatted into prefetch context (1–100). |
| `min_confidence` | `null` | Drop recalled memories below this confidence (0.0–1.0). |
| `session_duration_hours` | `null` | Override Memanto session lifetime. |

| Environment variable | Description |
|----------------------|-------------|
| `MOORCHEH_API_KEY` | Moorcheh API key (required). |
| `MEMANTO_AGENT_ID` | Override the agent id (takes priority over the config file). |

## Tools exposed to Hermes

| Tool | Description |
|------|-------------|
| `memanto_remember` | Store a durable fact, preference, decision, goal, or instruction. |
| `memanto_recall` | Search memories by semantic similarity. |
| `memanto_answer` | Answer a question grounded only in stored memories (RAG). |

Memory types follow Memanto's taxonomy: `fact`, `preference`, `goal`,
`decision`, `artifact`, `learning`, `event`, `instruction`, `relationship`,
`context`, `observation`, `commitment`, `error`.

## Development

```bash
pip install -e ".[dev]"
pytest          # provider unit tests (no network; SdkClient is faked)
ruff check .
```

## How it relates to the other integrations

| Integration | Package | What it does |
|-------------|---------|--------------|
| `integrations/mcp` | `memanto-mcp` | MCP server for any MCP-compatible client (Claude, Cursor). |
| `integrations/crewai` | `crewai-memanto` | CrewAI tools for multi-agent memory sharing. |
| `integrations/hermes-agents` | `hermes-memanto` | **This** — a memory provider for the Hermes agent. |

All three talk to the same Moorcheh-backed Memanto agents, so memory written by
one is recallable from the others when they share an `agent_id`.

## Support

- [Memanto Documentation](https://docs.memanto.ai)
- [Moorcheh API Keys](https://console.moorcheh.ai/api-keys)
- [Hermes agent](https://github.com/NousResearch/hermes-agent)
