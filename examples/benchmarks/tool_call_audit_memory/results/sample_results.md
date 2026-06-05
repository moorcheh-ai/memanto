# Tool-Call Audit Memory Results

| Backend | Accuracy | Avg retrieved tokens | p95 latency ms | Stale conflict rate | Secret leak rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| append_only_log | 11.1% | 40.22 | 0.0671 | 55.6% | 11.1% |
| windowed_recent_log | 22.2% | 23.89 | 0.0154 | 22.2% | 0.0% |
| active_audit_digest | 100.0% | 32.67 | 0.0406 | 0.0% | 0.0% |

The active digest keeps one current fact per memory key, redacts secret-shaped values, and retrieves only facts relevant to each question. The append-only and recent-window baselines demonstrate the tradeoff between stale context bloat and lost long-term recall.
