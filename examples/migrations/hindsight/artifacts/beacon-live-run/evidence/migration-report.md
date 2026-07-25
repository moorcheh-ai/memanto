# Hindsight → OKF migration report

## Actual migration

| Measure | Result |
|---|---:|
| Hindsight source records | 35 |
| Active records mapped | 32 |
| Invalidated records archived | 3 |
| Skipped by Memanto dry run | 0 |
| Event | 12 |
| Fact | 17 |
| Learning | 3 |
| Source golden-set recall | 8/8 |

The source snapshot is 40,218 bytes. The human-readable OKF input
bundle is 128,341 bytes across 45 files, or
3.1911× the snapshot size. The 88,123-byte
change reflects OKF frontmatter, provenance, indexes, and an audit archive
rather than an attempt to optimize for compact storage.

## Savings disclosure

No provider savings figure is claimed.

The shipped `memanto migrate okf` command deliberately has no `--report`
option, unlike supported-provider migrations. This Path B adapter also uses a
local Hindsight source, so there is no honest provider token, latency, storage,
or billing baseline from which to calculate dollar savings. Inventing one
would be misleading. The exact storage delta above is reported instead.

See `memanto-dry-run.txt` for the captured real CLI output and
`source-recall.json` for every source-side answer and score.
