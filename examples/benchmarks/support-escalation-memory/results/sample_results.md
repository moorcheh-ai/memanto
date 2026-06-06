# Support Escalation Memory Benchmark

A deterministic benchmark for long-running support cases where plan, SLA, owner,
region, severity, rollback window, and erased secrets change across handoffs.

| Strategy | Accuracy | Stale leak rate | Avg retrieved tokens | p95 latency ms |
| --- | ---: | ---: | ---: | ---: |
| active_case_digest | 1.000 | 0.000 | 1.88 | 0.0008 |
| append_only_log | 0.875 | 0.625 | 18.62 | 0.0028 |
| recent_window_log | 0.500 | 0.125 | 4.62 | 0.0010 |
