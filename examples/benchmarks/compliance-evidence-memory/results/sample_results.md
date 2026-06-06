# Compliance Evidence Memory Results

| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency (s) | Stale Conflict Rate | Missing Evidence Rate | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active_evidence_digest | 100.0% | 9.40 | 0.015120 | 0.0% | 0.0% | 100.0% |
| append_only_log | 80.0% | 18.40 | 0.023960 | 100.0% | 0.0% | 39.1% |
| recent_window_log | 20.0% | 7.40 | 0.015760 | 40.0% | 60.0% | 24.3% |

The offline active digest models Memanto-style current-state distillation.
The append-only and recent-window baselines model passive memory layers with stale or incomplete recall.
