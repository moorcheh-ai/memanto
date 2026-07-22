# Migration and round-trip evidence

| Stage | Records | Files | Bytes |
| --- | ---: | ---: | ---: |
| LangGraph SQLite | 21 checkpoints | 1 | 81920 |
| First OKF bundle | 8 memories | 11 | 6481 |
| Memanto round-trip OKF | 8 memories | 19 | 16616 |

- Memanto import: 8 imported, 0 failed.
- Recall after round trip: 5/5 (1.0 parity).
- First portable bundle size change against the raw SQLite file: 92.1% smaller.

## Scope note

Raw SQLite file bytes compared with the first portable OKF bundle. This does not estimate provider token, latency, or billing savings.
