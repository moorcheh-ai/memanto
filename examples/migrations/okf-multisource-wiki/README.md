# Multi-source lock-in → consolidated OKF memory wiki

**Path C (OKF Renaissance)** showcase for [Bounty #1609](https://github.com/moorcheh-ai/memanto/issues/1609).

Most agents do not keep memory in one place. This demo starts from **two real
proprietary stores** that a coding assistant actually filled over six weeks,
consolidates them into one coherent portable wiki, and proves recall parity —
then hands the bundle to the shipped CLI:

```text
Chroma (vectors)  ─┐
                   ├─ adapters ─ consolidate ─ OKF wiki ─ memanto migrate okf ─ Memanto
SQLite (ad-hoc)   ─┘
```

No re-implementation of `memanto migrate`. Adapters **feed** OKF; Memanto owns import.

## Why this path

| Path B adapters (ChatGPT / LangGraph / …) | This Path C workflow |
| --- | --- |
| One source → OKF | **Two lived-in sources → one owned wiki** |
| File dump | Contradiction resolution + superseded timeline |
| Opaque lock-in | Git-friendly markdown humans can review |

## Quick start (< 15 minutes)

```bash
cd examples/migrations/okf-multisource-wiki
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional, for the official dry-run:
pip install -e ../../..

python run.py --force --update-sample
memanto migrate okf out/okf-bundle --dry-run
```

No Moorcheh key is required for seeding, consolidation, or the OKF dry-run.
Set `MOORCHEH_API_KEY` only if you want a live import afterward.

## What the seeder actually does

1. **`seed_chroma.py`** — real `chromadb.PersistentClient` run. Fourteen memories
   across six weekly sessions, including a preference **correction**
   (TypeScript → Python/FastAPI) with `supersedes`.
2. **`seed_sqlite_store.py`** — real SQLite `agent_memories` table. Eight rows
   that overlap Chroma on identity/timezone/on-call, carry a **stale**
   TypeScript preference, and add unique ops facts (CI, budget, runbook).

Hand-written export JSON is not the source of truth — the stores are.

## Migration summary (committed sample)

From the committed `sample/` artifacts (`python run.py --force --update-sample`):

| Metric | Value |
| --- | ---: |
| Chroma source records | 14 |
| SQLite source records | 8 |
| Active consolidated memories | 17 |
| Archived superseded / conflicts | 2 |
| Golden recall (consolidated source) | 8/8 |
| Golden recall (OKF bundle) | 8/8 |
| `memanto migrate okf --dry-run` | 17 mapped, 0 skipped |

Savings report: OKF is a local format; the shipped importer documents that
`migrate okf` does **not** emit provider-style token/latency savings. This
showcase therefore reports storage shape (opaque vectors + SQLite rows →
readable markdown) instead of inventing Mem0-style dollar savings.

## Mapping table

Full concept → field table: [`MAPPING.md`](MAPPING.md).

## Round-trip validation

```bash
python -m pytest tests -q
```

Golden questions live in `golden_questions.json`. The parity report asserts the
consolidated corpus and the OKF bundle both answer every probe, including the
**current** language preference (Python/FastAPI) and not the stale TypeScript
backend preference.

## Sample OKF bundle

[`sample/okf-bundle/`](sample/okf-bundle/) — open any `memories/**/*.md` file.
Superseded history is under `sessions/` so it stays auditable without being
re-imported.

## Demo video checklist

Record a 2-minute screen capture covering:

1. Chroma + SQLite seed counts printing in the terminal
2. Consolidation summary (active / archived)
3. Opening an OKF markdown file in the editor
4. `memanto migrate okf out/okf-bundle --dry-run`
5. `recall-parity.md` showing 8/8

Then post with the required tags (`@moorcheh_ai`, YouTube `@moorchehai`,
LinkedIn company page) and claim on
[BountyHub](https://www.bountyhub.dev/bounty/view/b21928e9-70dd-4d95-adc6-3009df47e9f5).

## Layout

```text
okf-multisource-wiki/
  run.py                 # one-command pipeline
  seed_chroma.py         # real Chroma source
  seed_sqlite_store.py   # real SQLite source
  adapters.py            # source → memory dicts
  consolidate.py         # merge + conflict rules
  okf_writer.py          # OKF v0.2 writer
  validate.py            # golden Q&A
  MAPPING.md
  golden_questions.json
  sample/                # committed evidence
  tests/
```
