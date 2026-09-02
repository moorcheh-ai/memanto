# AI Chat Exports → Memanto OKF Migration Adapter

> Bounty #1609 · Path B — a new migration path for unsupported sources.
> Lives at `examples/migrations/ai-chat-exports/` in the `memanto` repo.

A modular Python ETL tool that converts AI chat exports (**ChatGPT, Claude,
Gemini**) into portable **OKF bundles** for Memanto migration.

Built **on top of** `memanto migrate okf` — this adapter generates the OKF
bundle; Memanto imports it. It is a **Path B** submission: a new migration
path for sources Memanto does not support natively, feeding the shipped CLI
rather than bypassing it.

```
Source Adapter → MemoryEntity → OKF Generator → OKF Bundle
                                                   ↓
                                       memanto migrate okf
                                     (import into Memanto)
```

## Layout

```
ai-chat-exports/
├── cli.py                 # build an OKF bundle from a real export
├── streamlit_app.py       # browser UI (select chats → OKF → import → export → answer)
├── generate_report.py     # migration summary + dry-run/export report
├── validate_roundtrip.py  # recall-parity check (before/after)
├── run.sh                 # single-command reproducibility
├── adapters/              # claude / chatgpt / gemini source adapters
├── core/                  # OKF generator, dedup, models, registry
├── docs/                  # mapping table + per-provider guides
├── tests/                 # pytest suite (34 tests)
├── validation/            # round-trip notes
└── okf_bundle/            # sample exported OKF artifact
```


## Quick Start

Create a virtualenv and install the dependency, then run the CLI:

```bash
python3 -m venv .venv && source .venv/bin/activate   # or activate your own
pip install -r requirements.txt                      # memanto CLI

# Convert ChatGPT export
python3 cli.py --source chatgpt --input ./export.json --output ./okf_output

# Convert Claude export
python3 cli.py --source claude --input ./conversations.json --output ./okf_output

# Convert Gemini export
python3 cli.py --source gemini --input ./conversations.json --output ./okf_output

# Dry run (preview only)
python3 cli.py --source claude --input ./conversations.json --dry-run

# Filter by keyword
python3 cli.py --source chatgpt --input ./export.json --filter "PostgreSQL"

# Filter by chat IDs
python3 cli.py --source chatgpt --input ./export.json --chats 1,5,12

# Interactive selection
python3 cli.py --source claude --input ./conversations.json --interactive

# Skip memories already imported (dedupe by source_ref against a prior OKF bundle)
python3 cli.py --source claude --input ./conversations.json --dedupe-from-dir okf_output
```

> A source does not have to be a local file. The pipeline is wired through
> `DataSource`, so an `api` source (live agent endpoint + injected creds) works
> the same way once an `ApiSourceAdapter` is registered:
>
> ```bash
> # Live agent / API source (endpoint + injected credentials via DataSource)
> python3 cli.py --source-type api --source agent --endpoint http://localhost:8000/memories
> ```
>
> See [Adding a Source](#adding-a-new-source).

> **Scalability note:** the adapter is a seam, not a one-off script. The same
> `SourceAdapter` protocol + `@register_adapter` registry means any future
> provider is one more package — file export or live agent — with zero pipeline
> changes. Today it ships ChatGPT, Claude, Gemini; tomorrow any source that
> speaks the protocol.

## Single-command reproducibility

`run.sh` builds one OKF bundle from a **real** exported chat archive in a
single command, then dry-runs the Memanto import:

```bash
./run.sh claude ./claude_export.zip
./run.sh chatgpt ./chatgpt_export/conversations.json
./run.sh gemini ./gemini_export/conversations.json
```

The source must be a **genuine exported archive** from the source tool — real
memories, not hand-written fixtures:
- **ChatGPT:** Settings → Data controls → Export data → `conversations.json`
- **Claude:** Settings → Export data → archive ZIP → `conversations.json`
- **Gemini:** Google Takeout → your chat JSON

See [docs/MAPPING.md](docs/MAPPING.md) for how each source maps onto Memanto.

## Full lifecycle (in → owned → portable)

```
1. Convert        python3 cli.py --source claude --input <export> --output ./okf_output
2. Import         memanto migrate okf ./okf_output --dry-run   (preview)
                  memanto migrate okf ./okf_output             (import)
3. Export out     memanto memory export --okf -o ~/.memanto/export   (portable OKF)
4. Recall parity  python3 validate_roundtrip.py --source claude \
                      --input <export> --questions Q1 Q2
```

Step 2 imports the bundle losslessly into the active Memanto agent. Step 3
closes the loop: the same memories come back out as a portable, git-friendly
OKF bundle owned by you. Note the memanto CLI requires the export path to live
**inside** the agent data directory (`~/.memanto/`).

Step 4 runs the same golden questions **before** migration (against the raw
export) and **after** (via `memanto answer`/`memanto recall`) and scores
recall parity. Requires `MOORCHEH_API_KEY` (`.env`) and an active agent.

## Web showcase

`streamlit_app.py` is a browser UI on top of `cli.py`: pick a source, load an
export, select conversations, generate the OKF bundle, and preview the result
without touching the terminal.

```bash
pip install streamlit
streamlit run streamlit_app.py
```

## Supported Sources

**Three adapters ship today** — ChatGPT, Claude, Gemini — each implemented
against the same `SourceAdapter` protocol, so a new source is just one more
package in the registry.

| Source | Export format | Status |
|--------|--------------|--------|
| ChatGPT | `conversations.json` (direct or ZIP) | Ready |
| Claude | `conversations.json` (direct or ZIP) | Ready |
| Gemini | `conversations.json` (direct or ZIP) | Ready |
| Zep/Graphiti | Graph export JSON | Planned |
| LangMem | LangChain export | Planned |

> **Sample bundle note:** the bundled `okf_bundle/` ships a de-identified
> sample with ChatGPT + Gemini memories only. The Claude adapter is fully
> implemented and tested, but its real conversational data is personal, so the
> sample omits it for privacy — generate your own with:
> `python3 cli.py --source claude --input <your-export> --output ./okf_output`.

## Architecture

- **Adapter Protocol** (`core/adapters.py`): each source implements
  `load()`, `extract()`, `get_conversation_list()`, `get_source_stats()`.
- **Sources are data-agnostic** (`core/adapters.py::DataSource`): a migration
  can come from a local file path **or** a live API endpoint. `load_source()`
  dispatches on `DataSource.kind` (`file` vs `api`), so the pipeline is never
  hard-wired to file paths.
- **Live/agent sources** (`core/adapters.py::ApiSourceAdapter`): adapters that
  pull from a running agent implement `load_source(DataSource)` and receive
  credentials **injected** via `DataSource` (they never read `os.getenv`
  themselves). This is the seam for future agent-to-agent migration (e.g.
  opencode-like agents) and future provider APIs.
- **Canonical Model** (`core/models.py`): `MemoryEntity` is the universal
  intermediate format.
- **OKF Generator** (`core/okf_generator.py`): produces valid OKF markdown
  with YAML frontmatter.

See [docs/MAPPING.md](docs/MAPPING.md) for the full source→OKF field mapping.

## Adding a New Source

**File-export source** (like the three shipped adapters):

1. Create `adapters/newsource.py`
2. Implement the `SourceAdapter` protocol
3. Decorate with `@register_adapter`
4. Import in `adapters/__init__.py`

**API / live-agent source:**

1. Create `adapters/agent.py`
2. Implement `ApiSourceAdapter` (`load_source(source: DataSource)`)
3. Read credentials from `source.credentials` (DI — no `os.getenv`)
4. Decorate with `@register_adapter` and import in `adapters/__init__.py`

No change to the OKF generator, dedup, or CLI pipeline is required — they only
see the `MemoryEntity` list that `extract()` returns.

## Tests

```bash
pytest
```

## Links

- [Memanto migrate CLI](https://docs.memanto.ai/cli/migrate/migrate)
- [OKF integration guide](https://docs.memanto.ai/integrations/okf)
- [Issue #1609](https://github.com/moorcheh-ai/memanto/issues/1609)
