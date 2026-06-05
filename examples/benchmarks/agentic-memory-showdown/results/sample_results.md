# shifting-persona-temporal-tracking

| Backend | Total Tokens Ingested | Total Tokens Retrieved | p95 Latency | Retrieval Accuracy |
| --- | ---: | ---: | ---: | ---: |
| memanto-active-memory | 78 | 32 | 0.000007s | 100.00% |
| graph-style-append-log | 78 | 98 | 0.000064s | 91.25% |

## Reproducibility Notes

- Every backend ingests the same chronological sessions and answers the same questions.
- Token counts use one deterministic counter so relative footprint is reproducible offline.
- The active-memory backend replaces stale state; the append-log backend preserves conflicts.
