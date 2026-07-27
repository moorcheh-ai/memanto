# Escape the graph: MCP Memory Server → Memanto OKF

This showcase migrates a real knowledge graph created by the official
`@modelcontextprotocol/server-memory` package into portable, readable
[Open Knowledge Format (OKF)](https://docs.memanto.ai/integrations/okf)
Markdown.

It proves the full freedom loop:

```text
official MCP tools → memory.jsonl → OKF Markdown → Memanto loader
                         ↑                         ↓
                         └── lossless rebuild ─────┘
```

## Why this source matters

The official MCP Memory Server is the reference knowledge-graph memory
implementation in `modelcontextprotocol/servers`. Its storage is compact and
useful, but it is a local JSONL graph. This adapter makes the graph readable,
git-friendly, linkable, importable by Memanto, and exactly reconstructable.

This is a new Path B migration source for bounty #1609. It does not duplicate
Memanto's shipped Mem0, Letta, Supermemory, or OKF importers.

## Setup and run the complete demo

From the Memanto repository root, install the project and its test tools once:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[all]'
```

Then run the one-command showcase:

```bash
.venv/bin/python examples/migrations/mcp-memory-server/run_demo.py
```

That command:

1. reads the included graph produced by the official MCP server;
2. writes one OKF document per entity;
3. feeds it through the shipped `memanto migrate okf --dry-run` CLI;
4. loads the bundle through Memanto's real `load_okf_bundle` and `map_okf`;
5. reconstructs the source JSONL from the Markdown documents;
6. runs five golden recall questions before and after migration.

No API key or network access is needed for the checked-in sample. The converter
and reconstructor are Python-standard-library only; the complete validation
uses the Memanto project environment installed above. The official CLI dry-run
writes its normal local preview artifact under `~/.memanto/migrate/okf/`, but
does not write any memories.

Expected headline result:

```text
source records reconstructed: 9/9
Memanto rows mapped: 5/5
Memanto CLI dry-run: 5 mapped, 0 skipped
Memanto type breakdown: artifact: 4, goal: 1
golden recall parity: 5/5 (100%)
```

## Regenerate the source with the official server

The checked-in source is not hand-authored JSON. `generate_real_source.py`
starts the official npm package, negotiates MCP over stdio, and calls
`create_entities`, `create_relations`, and `add_observations` across three
sessions.

With Node.js/npm available, regenerate the source and run the full pipeline:

```bash
.venv/bin/python examples/migrations/mcp-memory-server/run_demo.py --regenerate
```

The generator pins
`@modelcontextprotocol/server-memory@2026.7.4` for reproducibility. The stored
memories describe the actual research and implementation decisions behind this
adapter, including the discarded LangGraph direction and the final lossless
design.

## Import into Memanto

After configuring and activating a Memanto agent:

```bash
memanto migrate okf sample/okf --dry-run
memanto migrate okf sample/okf
```

The bundle puts importable documents under `memories/`. Metrics and the
original source live outside that directory and are therefore not re-ingested.
The dry-run path does not require an API key. The second command performs a live
import and therefore requires a configured Moorcheh/Memanto account.

## Output layout

```text
sample/okf/
├── index.md
├── memories/
│   ├── index.md
│   └── entities/
│       └── <one readable document per MCP entity>.md
├── metrics/
│   ├── mapping-table.md
│   ├── memanto-cli-dry-run.json
│   ├── migration-report.json
│   └── round-trip-validation.json
└── source/
    └── memory.jsonl
```

Every entity document contains:

- the entity name and type;
- every observation in source order;
- typed outgoing links and incoming backlinks;
- a fenced `mcp-memory-source` JSON block with original line numbers and exact
  source records.

`reconstruct_mcp_memory.py` rebuilds the JSONL from those embedded blocks:

```bash
python reconstruct_mcp_memory.py \
  --input sample/okf \
  --output /tmp/reconstructed-memory.jsonl
```

## Mapping and fidelity

| MCP Memory concept | OKF representation | Result |
| --- | --- | --- |
| Entity name | `title` + H1 | Memanto memory title |
| Entity type | Free-form `type` + exact source metadata + `x_memanto.type` | Known types map deterministically; unknown types become `observation` |
| Observation | Numbered Markdown item | Searchable content |
| Relation | Typed Markdown link/backlink | Human-browsable graph neighborhood |
| Exact record | Embedded JSON source block | Lossless reconstruction |
| Source URI | `memory://` resource URI | Memanto `source_ref` |

The converter fails closed on malformed JSON, duplicate entities or relations,
unknown record types, and dangling relation endpoints. It never silently drops
source data.

## Tests

From the repository root:

```bash
.venv/bin/pytest -q examples/migrations/mcp-memory-server/tests
.venv/bin/ruff check examples/migrations/mcp-memory-server
.venv/bin/ruff format --check examples/migrations/mcp-memory-server
```

The tests cover Memanto consumability, lossless reconstruction, embedded
Markdown fences, invalid UTF-8, slug collisions, dangling references, and
deterministic output.

## Privacy and security

Memory graphs can contain private facts. The converter is fully offline, but
you should inspect an output bundle before committing or sharing it. The
included sample contains only public project research and no credentials or
personal data.

## Demo recording script

See [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for a tight two-minute recording plan
covering source creation, migration, readable Markdown, reconstruction, and
100% recall parity.
