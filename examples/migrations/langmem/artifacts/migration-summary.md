# Migration summary — LangMem -> Memanto (OKF)

- Extraction backend: **replay**
- Source LangMem memories: **10**
- Mapped Memanto memories: **10**
- OKF bundle sections: memories, metrics

## Type breakdown (inferred from untyped LangMem content)

| Memanto type | Count |
| --- | :---: |
| decision | 1 |
| fact | 2 |
| goal | 2 |
| preference | 4 |
| relationship | 1 |

## Recall parity (before vs after)

- Before (LangMem): 7/7 (100.0%)
- After (Memanto):  7/7 (100.0%)
- Parity: 100.0%

See `validation-report.md` for the per-question breakdown and `okf-bundle/` for the human-readable, portable memory bundle.
