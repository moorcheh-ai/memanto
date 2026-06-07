# Security Review Evidence Memory Results

| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency ms | Cross-Session Degradation | Stale Conflict Rate | Secret Leak Rate | Evidence Coverage | Signal/Noise |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| active_security_digest | 100.00% | 114.00 | 0.0087 | 0.00% | 0.00% | 0.00% | 100.00% | 0.0292 |
| passive_graph_memory | 0.00% | 198.00 | 0.0037 | 100.00% | 83.33% | 100.00% | 100.00% | 0.0168 |
| append_only_log | 0.00% | 154.00 | 0.0006 | 100.00% | 66.67% | 100.00% | 95.00% | 0.0206 |
| recent_window_log | 33.33% | 83.00 | 0.0003 | 100.00% | 33.33% | 0.00% | 75.00% | 0.0301 |

## Session Accuracy Curves

- `active_security_digest`: s1-initial-review=100%, s2-triage-and-retTest=100%, s3-follow-up-review=100%, s4-remediation-review=100%
- `passive_graph_memory`: s1-initial-review=0%, s2-triage-and-retTest=0%, s3-follow-up-review=0%, s4-remediation-review=0%
- `append_only_log`: s1-initial-review=0%, s2-triage-and-retTest=0%, s3-follow-up-review=0%, s4-remediation-review=0%
- `recent_window_log`: s1-initial-review=0%, s2-triage-and-retTest=0%, s3-follow-up-review=0%, s4-remediation-review=0%

The active security digest keeps current normalized facts, redacts synthetic secrets, and suppresses stale statuses.
