# Release Readiness Memory Benchmark Results

| Backend | Accuracy | Avg retrieved tokens | p95 latency ms | Stale conflict rate | Secret leak rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| active_release_digest | 100.0% | 9.14 | 0.0015 | 0.0% | 0.0% |
| append_only_log | 28.6% | 15.57 | 0.002 | 28.6% | 14.3% |
| recent_window_log | 71.4% | 10.0 | 0.005 | 14.3% | 14.3% |

The active digest represents a Memanto-style strategy: keep the current release facts by topic, suppress stale handoff notes, and never retrieve synthetic secrets.
The append-only and recent-window baselines model common memory shortcuts that either over-retrieve stale state or miss older still-current constraints.
