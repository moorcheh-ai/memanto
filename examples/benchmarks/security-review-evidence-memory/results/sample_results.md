# Security Review Evidence Memory Results

| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency ms | Stale Conflict Rate | Secret Leak Rate | Evidence Coverage | Signal/Noise |
|---|---:|---:|---:|---:|---:|---:|---:|
| active_security_digest | 100.00% | 114.00 | 0.0060 | 0.00% | 0.00% | 100.00% | 0.0292 |
| passive_graph_memory | 0.00% | 198.00 | 0.0056 | 83.33% | 100.00% | 100.00% | 0.0168 |
| append_only_log | 0.00% | 154.00 | 0.0006 | 66.67% | 100.00% | 95.00% | 0.0206 |
| recent_window_log | 33.33% | 83.00 | 0.0003 | 33.33% | 0.00% | 75.00% | 0.0301 |

The active security digest keeps current normalized facts, redacts synthetic secrets, and suppresses stale statuses.
