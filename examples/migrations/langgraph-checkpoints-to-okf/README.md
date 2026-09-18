# LangGraph Checkpoints → OKF — free your agent's checkpointed memory

**Path B (New Frontier) showcase for the Great Memory Migration bounty.**

Every LangGraph agent that uses persistence accumulates its learned context —
user preferences, corrections, resolved contradictions — inside a binary
checkpointer blob (SQLite/Postgres). Switch memory systems and it all
evaporates. This adapter turns a real LangGraph `SqliteSaver` checkpoint
store into a portable, human-readable **OKF bundle** that Memanto's shipped
tooling imports losslessly:

```text
LangGraph checkpoints.sqlite  ──adapter──▶  OKF markdown bundle  ──memanto migrate okf──▶  Memanto
        (locked in)                        (you own it)                     (portable)
```

**In → owned → portable.** No core changes — the adapter *feeds* the shipped
CLI; it doesn't reimplement it.

## Quickstart (< 15 min)

```bash
pip install -r requirements.txt
python run.py            # seed a lived-in agent → migrate → validate
```

Then prove Memanto accepts the bundle (no API key needed for dry-run):

```bash
pip install memanto
memanto migrate okf out/okf-bundle --dry-run
```

Expected dry-run output: **11 OKF nodes → 11 mapped memories, 0 skipped.**

Full live import (writes into Memanto's engine, free tier):

```bash
export MOORCHEH_API_KEY=...   # free key at https://moorcheh.ai
memanto migrate okf out/okf-bundle
```

## What the pipeline does

| Step | File | What happens |
|------|------|--------------|
| 1. Seed | `seed_agent.py` | Runs a **real LangGraph StateGraph** — a travel-planner agent accumulating memories over 7 sessions across 2 threads (incl. a *resolved contradiction*: "vegetarian" → "eating meat again"). Every turn is persisted by LangGraph's `SqliteSaver` into `checkpoints.sqlite`. Deterministic rule-based extraction keeps the demo 100% reproducible with zero API keys. |
| 2. Migrate | `adapter.py` | **Discovers every thread stored in the checkpoint DB** (no hard-coded list — any real store works), reads the latest checkpoint per thread via LangGraph's **official reader API**, and emits one OKF markdown document per memory into `out/okf-bundle/memories/`, plus `out/migration_summary.json` (source records → mapped docs, per-type & per-thread breakdown). |
| 3. Validate | `validate.py` | Golden Q&A set: 9 probe questions (name, seat, airport, budget, diet status, loyalty number, policies) must be answerable from **both** the source store and the OKF bundle. Prints recall parity — **9/9 (100%)**. |

## Mapping table (LangGraph → OKF/Memanto)

| LangGraph concept | OKF field | Notes |
|---|---|---|
| `thread_id` | `resource`, `tags`, extra `thread_id` | one `langgraph-checkpoint://<thread>` resource per conversation |
| checkpoint `channel_values["memories"]` record | one OKF document | title = memory text |
| record `kind` (`preference`, `fact`, `decision`, `commitment`, `constraint`) | `type` + `x_memanto.type` | OKF type is free-form; `x_memanto.type` set only when it matches a Memanto memory type, else Memanto auto-classifies |
| record `ts` | `timestamp` | original creation time preserved |
| checkpoint `id` / `step` | extras + body Provenance | full audit trail |
| extraction `rule` | extra `extraction_rule` | reproducibility evidence |

Extras have no OKF schema slot, so Memanto's loader preserves them losslessly
into the `[Supporting data]` footer — nothing is dropped.

## Fidelity evidence

- `out/migration_summary.json` — 11 source records → 11 OKF docs (per-type:
  preference 4, fact 3, constraint 2, decision 1, commitment 1)
- `out/validation.json` — recall parity 100%
- `out/okf-bundle/` — the artifact itself, human-inspectable markdown
- `tests/test_adapter.py` — includes the acceptance test that loads the
  bundle **through Memanto's own `okf_loader` + `map_okf`** and asserts zero
  dropped records, intact extras, and correct type breakdown
  (`5 passed` via `pytest -c pytest.ini`)

## Demo video

`demo.mp4` — terminal recording of the real pipeline: seeding the agent,
running the adapter, the 9/9 parity check, and the genuine
`memanto migrate okf --dry-run` accepting the bundle.

## Why this matters (the story)

LangGraph is the most deployed agent orchestration framework, and its
checkpoint model is where long-running agents *actually keep what they
learn*. That memory is real user value trapped in a binary store. This
adapter is a permanent migration path: anyone can point it at their own
`checkpoints.sqlite` and walk away with portable markdown they own — then
import it into Memanto, or anywhere else OKF flows.

## Files

```text
seed_agent.py      # real LangGraph run → checkpoints.sqlite
adapter.py         # checkpoints → OKF bundle (the deliverable)
validate.py        # golden Q&A recall parity
run.py             # single-command pipeline
tests/             # incl. memanto-loader acceptance test
make_demo.py       # regenerates demo.mp4 from a real captured run
demo.mp4           # terminal recording of the real run
out/okf-bundle/    # the committed OKF artifact
```
