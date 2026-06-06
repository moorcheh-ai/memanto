# Security Review Evidence Memory Results

| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency ms | Stale Conflict Rate | Secret Leak Rate | Evidence Coverage | Signal/Noise |
|---|---:|---:|---:|---:|---:|---:|---:|
| active_security_digest | 100.00% | 114.00 | 0.0071 | 0.00% | 0.00% | 100.00% | 0.0292 |
| append_only_log | 0.00% | 154.00 | 0.0007 | 66.67% | 100.00% | 95.00% | 0.0206 |
| recent_window_log | 33.33% | 83.00 | 0.0004 | 33.33% | 0.00% | 75.00% | 0.0301 |

The active security digest keeps current normalized facts, redacts synthetic secrets, and suppresses stale statuses.
