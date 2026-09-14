# Savings Report

## Result

Provider savings report: **not applicable for OKF import**.

Memanto's shipped `migrate okf` command explicitly describes OKF as a local
file bundle with "no API key and no savings report." This Path B adapter feeds
that supported command directly, so reporting invented token, latency, or
storage savings would be misleading.

## Auditable Portability Metrics

| Metric | Value |
| --- | ---: |
| Codex source records | 1 |
| Codex task blocks | 1 |
| Mapped OKF memories | 1 |
| Skipped records | 0 |
| Source JSON bytes | 4,650 |
| Complete OKF bundle bytes | 3,607 |
| Source golden recall | 100% |
| OKF golden recall | 100% |
| Recall parity delta | 0 points |
| API calls during conversion and dry-run | 0 |

The byte counts compare different container formats and are evidence of artifact
size, not a claimed storage saving.
