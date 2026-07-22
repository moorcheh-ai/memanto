# Migration and round-trip evidence

Run ID: `20260722T223523Z-27da3254`

| Stage | Records | Files | Bytes |
| --- | ---: | ---: | ---: |
| LangGraph SQLite | 21 checkpoints | 1 | 81920 |
| First OKF bundle | 8 memories | 11 | 6497 |
| Memanto round-trip OKF | 8 memories | 19 | 16721 |

- First OKF type breakdown: artifact=2, decision=1, fact=2, goal=1, preference=2.
- Round-trip recovery: 8/8 portable memories exported from Memanto.
- Recall after round trip: 5/5 (1.0 parity).
- Memanto import: 8 imported, 0 failed.
- First portable bundle size change against the raw SQLite file: 92.1% smaller.

## Scope note

Raw SQLite file bytes compared with the first portable OKF bundle. This does not estimate provider token, latency, or billing savings.
