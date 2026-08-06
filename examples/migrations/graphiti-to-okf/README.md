# Graphiti → Memanto → OKF (with Mem0 consolidation)

> **Own your agentic memory.** Move a real temporal knowledge graph out of
> Zep/Graphiti, into Memanto, out again as a portable OKF bundle — then merge
> a second source (Mem0) into the same agent and prove the consolidation with
> a directory diff.
>
> Covers bounty [#1609](https://github.com/moorcheh-ai/memanto/issues/1609)
> **Path B** (new unsupported adapter) **and Path C** (multi-source OKF
> consolidation) in one PR.

## Why this exists

`memanto migrate` already speaks Mem0, Letta, Supermemory, and OKF. It does
**not** speak Graphiti. Graphiti's whole differentiator is bi-temporality
(`valid_at` / `invalid_at` on every fact edge) — exactly the information a
flat chat-log adapter throws away. This example is the missing adapter, plus
the Path C payoff nobody else in the bounty is doing: two real sources, one
portable memory.

**This adapter does not reimplement the CLI.** It transforms. Import,
savings report, OKF export, and answer all go through the shipped
`memanto` commands.

```
Graphiti (Neo4j/FalkorDB/Kuzu)
        │  scripts/populate_graphiti.py   ← real multi-session conversation
        │  scripts/export_graphiti.py     ← untouched raw dump
        ▼
data/graphiti_raw_export.json
        │  scripts/graphiti_to_memanto.py ← THIS adapter
        ├──────────────────────────────► data/graphiti_okf_bundle/     (recommended)
        └──────────────────────────────► data/memanto_provider_import.json  (savings report only)
        │
        │  memanto migrate okf …          ← shipped CLI
        ▼
Memanto agent
        │  memanto memory export --okf    ← shipped CLI
        │  scripts/populate_mem0.py + memanto migrate mem0 …
        ▼
okf_bundle_sample/   +   data/consolidation_diff.txt
```

## Setup (< 15 minutes)

### Prerequisites

- Python 3.10–3.12
- Docker Desktop **or** set `GRAPHITI_BACKEND=kuzu` for the zero-Docker fallback
- Keys (free tiers are fine):
  - [Moorcheh](https://www.moorcheh.ai) → `MOORCHEH_API_KEY`
  - OpenAI / Gemini / Anthropic → Graphiti's extraction LLM
  - Anthropic → Phase 3 judge (`ANTHROPIC_API_KEY`)
  - [Mem0](https://app.mem0.ai) → Phase 4 consolidation (`MEM0_API_KEY`)

### Install

```bash
# from the memanto repo root
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .                   # installs the memanto CLI
cd examples/migrations/graphiti-to-okf
pip install -r requirements.txt
cp .env.example .env               # then fill the keys
```

### One command

```bash
# Linux / macOS
bash scripts/run_all.sh

# Windows
powershell -ExecutionPolicy Bypass -File scripts/run_all.ps1
```

That single command: starts Neo4j → populates Graphiti → exports → adapts →
dry-runs both import paths → imports via OKF → validates with the Anthropic
judge → exports OKF → migrates Mem0 into the same agent → re-exports → writes
the consolidation diff.

## Mapping table (approved)

See [`data/mapping_table.md`](data/mapping_table.md) for the full table. Headline:

| Graphiti | Memanto | Why |
| --- | --- | --- |
| `EntityEdge` | `fact` (refined by relation name → preference/decision/…) | Atomic knowledge + bi-temporal interval |
| `EntityNode` | `context` | Durable subject summaries |
| `EpisodicNode` | `observation` | Raw utterances |
| `CommunityNode` | `learning` | Synthesised cluster summaries |

Temporal intervals survive three ways: prose in the body, OKF frontmatter
(`valid_at`/`invalid_at`/`expired_at`), and `current`/`superseded` tags.
Confidence is derived from temporal standing (0.9 current / 0.5 superseded),
never invented.

## Artifacts this produces

| Path | What |
| --- | --- |
| `data/graphiti_raw_export.json` | Untouched Graphiti dump (real) |
| `data/graphiti_okf_bundle/` | Adapter → OKF (recommended import) |
| `data/memanto_provider_import.json` | Adapter → Mem0-shaped JSON (savings report only) |
| `data/mapping_table.md` | Concept + field + per-run counts |
| `data/savings_report.txt` | Real CLI `migrate-report.md` |
| `data/validation_results.md` | Before/after Q&A + parity % |
| `data/consolidation_diff.txt` | Pre- vs post-Mem0 OKF directory diff |
| `okf_bundle_sample/` | Final post-consolidation OKF bundle |

## Savings report

_Filled by the live run. Tonight: blocked on missing `MOORCHEH_API_KEY` —
see [`BLOCKERS.md`](BLOCKERS.md). After you run `run_all`, the real CLI
output lands in `data/savings_report.txt` and is pasted here._

## Round-trip validation

12 golden questions specifically probe temporal structure (e.g. "what did I
prefer for IaC before I changed my mind, and when?"). Before = live Graphiti
search hits. After = `memanto answer`. Score = Anthropic LLM-as-judge,
temperature 0, fixed rubric. Results → `data/validation_results.md`.

_Tonight: blocked on missing LLM / Moorcheh / Anthropic keys._

## Two sources, one portable memory (Path C)

After the Graphiti-derived agent is loaded, `scripts/populate_mem0.py`
builds a second, smaller **real** Mem0 store for the same person/project
(Daniel Okafor / Atlas / Halcyon), including one mid-store correction
(Friday → Monday changelog). That store is migrated into the **same**
`agent_id` via `memanto migrate mem0 --file`, the OKF bundle is re-exported,
and `data/consolidation_diff.txt` shows exactly what the merge added.

## Demo video

_Link goes here after recording._ Show: live Graphiti → `memanto migrate` →
savings report → OKF bundle → agent answering a temporal question correctly →
Mem0 merge → consolidation diff.

## Overnight status

See [`SUMMARY.md`](SUMMARY.md) for what ran, what is blocked, and the
morning checklist (demo video, social, PR, BountyHub claim).

## Dev checks (no keys required)

```bash
pytest -c pytest.ini
ruff check graphiti_okf scripts tests
```
