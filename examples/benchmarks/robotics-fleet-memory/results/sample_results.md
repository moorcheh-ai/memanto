# Robotics Fleet Memory Benchmark Results

Dataset: robotics_fleet_memory (2026-06-15)
Events: 12
Queries: 7
Iterations per query: 50

| Backend | Accuracy | Retrieved tokens | Avg retrieved tokens | Stale conflict rate | Secret leak rate | p95 latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| append_only_log | 0.143 | 222 | 31.71 | 0.714 | 0.143 | 0.6354 |
| recent_window | 0.571 | 141 | 20.14 | 0.143 | 0 | 0.353 |
| active_fleet_digest | 1 | 69 | 9.86 | 0 | 0 | 0.3195 |

## Per-query failures

### append_only_log
- r17-current-assignment: stale: aisle A, replenishment
- r42-safety-state: stale: lidar anomaly, safety hold
- dock-3-current-state: stale: closed, wheel-stop repair, Route cold-chain arrivals to Dock 2
- zone-f-cold-chain-rule: stale: manual override, bypass
- dispatch-owner-current: stale: Milo Tan
- credential-suppression: missing: sensitive credentials suppressed; leak: TEMP-SECRET-7781, vendor API token

### recent_window
- r17-current-assignment: missing: R-17, Dock 4, express, manifest
- zone-f-cold-chain-rule: stale: manual override
- credential-suppression: missing: sensitive credentials suppressed

### active_fleet_digest

No failures.
