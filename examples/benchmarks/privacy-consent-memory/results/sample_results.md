# Privacy Consent Memory Benchmark Results

| Backend | Accuracy | Stale Leak | Erased Leak | Avg Tokens | p95 Latency | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active_consent_digest | 100.0% | 0.0% | 0.0% | 1.3 | 0.001 ms | 0.7778 |
| append_only_log | 0.0% | 57.1% | 28.6% | 17.7 | 0.001 ms | 0.0000 |
| recent_window_log | 28.6% | 14.3% | 0.0% | 3.3 | 0.001 ms | 0.0870 |
