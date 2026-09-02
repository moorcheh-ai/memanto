# Migration Summary

## Live run — all three sources imported into Memanto (0 failures)

| Provider | Source conversations | Memory entities mapped | Imported | Failed |
|----------|---------------------|------------------------|----------|--------|
| ChatGPT | 7 | 7 | 7 | 0 |
| Gemini | 10 | 10 | 10 | 0 |
| Claude | 17 | 17 | 17 | 0 |
| **TOTAL** | **34** | **34** | **34** | **0** |

## Per-type breakdown

| Type | Count |
|------|-------|
| context | 34 |

Every conversation maps to one `context` memory; provenance `explicit_statement`, resource URI preserved (`chatgpt://`, `gemini://`, `claude://`), full message transcript retained in the body. Classification is done by the Memanto parsing service on import.

## Portable export (out leg)

Pass `--export-memanto <dir>` to `generate_report.py` to run `memanto memory export --okf` and prove the portable out-leg. The export path must live inside the agent data directory (e.g. `~/.memanto/export`).

## `memanto migrate okf --dry-run` output (chatgpt sample)

```
OKF -> Memanto  Dry run
… Loading OKF bundle from okf_output/chatgpt
… Mapping OKF nodes onto Memanto schema...
Dry run complete
OKF nodes: 7
Mapped memories: 7  (skipped 0)
Type breakdown: context: 7
Dry run — no writes performed.
Run dir: ~/.memanto/migrate/okf/20260830_235456/mapped_preview.json
```

Identical funnel for Gemini (10 → 10 → 0) and Claude (17 → 17 → 0). Full per-provider dry-run evidence can be regenerated with:

```bash
python3 generate_report.py --source chatgpt --input ./export.json --output ./okf_output/chatgpt
python3 generate_report.py --source gemini --input ./conversations.json --output ./okf_output/gemini
python3 generate_report.py --source claude --input ./conversations.json --output ./okf_output/claude
```