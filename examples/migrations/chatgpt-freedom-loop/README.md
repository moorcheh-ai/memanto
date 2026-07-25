# ChatGPT → Memanto → OKF Freedom Loop

**Path B showcase for [#1609](https://github.com/moorcheh-ai/memanto/issues/1609)** — liberate the memory your ChatGPT assistant has built about you.

```
ChatGPT export (conversations.json)
        │
        ▼
memanto migrate chatgpt --file ./data/conversations.json --dry-run --report
        │
        ▼
Memanto agent memories (owned)
        │
        ▼
memanto memory export --okf ./okf_sample
        │
        ▼
Portable markdown OKF bundle (yours forever)
```

## Why this exists

ChatGPT stores years of preferences, decisions, and context in a proprietary tree-shaped export. Memanto already ships `memanto migrate` + OKF export. This showcase adds the **missing ChatGPT adapter** and a reproducible end-to-end demo so anyone can run the freedom loop in under 15 minutes.

## Quick start

```bash
# From this directory (or after copying into examples/migrations/chatgpt-freedom-loop/)
./run.sh

# Or step-by-step:
python3 scripts/generate_sample_export.py   # builds data/conversations.json
python3 scripts/map_and_report.py           # maps + writes reports/ + okf_sample/
```

With a live Memanto install + Moorcheh key:

```bash
export MOORCHEH_API_KEY=...   # from https://moorcheh.ai/
memanto migrate chatgpt --file ./data/conversations.json --dry-run --report
memanto migrate chatgpt --file ./data/conversations.json
memanto memory export --okf ./okf_live
```

## What's in this folder

| Path | Purpose |
|------|---------|
| `data/conversations.json` | ChatGPT-shaped export (tree `mapping`, multimodal, branching edits) |
| `scripts/generate_sample_export.py` | Reproducible generator for the sample archive |
| `scripts/map_and_report.py` | Offline map → summary report + OKF sample (no API key required) |
| `reports/migration_summary.md` | Source → mapped counts + type breakdown |
| `MAPPING.md` | ChatGPT concepts → Memanto / OKF field table |
| `okf_sample/` | Human-inspectable OKF v0.1 bundle |
| `run.sh` | Single-command demo |

## Real exports

1. ChatGPT → Settings → Data controls → **Export data**
2. Unzip the archive
3. Point the CLI at it:

```bash
memanto migrate chatgpt --file ~/Downloads/chatgpt-export/ --dry-run --report
```

The sample under `data/` mirrors the real `conversations.json` schema so the same commands work unchanged on your own export.

## Demo video / social (required for #1609 payout)

- **Demo video:** _(attach screen recording URL in PR description)_
- **Social posts:** tag `@moorcheh_ai` (X) / Moorcheh YouTube / LinkedIn company page
- **BountyHub:** claim #1609 and attach this PR before **2026-08-31 23:59 UTC**

## Mapping table

See [`MAPPING.md`](./MAPPING.md).

## Tests

Adapter unit tests live with the mapper:

```bash
python -m pytest tests/test_chatgpt_migration.py -v
```
