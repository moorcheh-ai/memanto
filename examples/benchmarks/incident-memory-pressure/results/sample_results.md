# Incident Memory Pressure Benchmark Results

| Backend | Tokens Ingested | Tokens Retrieved | p95 Latency (ms) | Retrieval Accuracy | Stale Suppression | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| memanto_typed_digest | 183 | 215 | 0.019 | 100.00% | 100.00% | 24.19% |
| append_only_log | 183 | 529 | 0.017 | 75.00% | 25.00% | 9.83% |

## Notes

- Accuracy rewards current expected facts and penalizes stale facts.
- Signal/noise rewards concise context that contains expected fact tokens.
- The default run is credential-free and deterministic.
