# Policy Drift Memory Benchmark Results

| Backend | Accuracy | Stale conflicts | Sensitive leaks | Avg retrieved tokens | Stored tokens | p95 latency proxy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| memanto_active_digest | 100.0% | 0.0% | 0.0% | 24.62 | 133 | 8.615 ms |
| append_only_log | 25.0% | 75.0% | 37.5% | 37.75 | 203 | 12.265 ms |
| recent_window_log | 12.5% | 37.5% | 0.0% | 13.38 | 64 | 5.270 ms |

The latency number is a deterministic proxy computed from scanned and retrieved token counts; it is not wall-clock timing.
