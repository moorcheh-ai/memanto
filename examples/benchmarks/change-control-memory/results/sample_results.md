# Change-Control Memory Benchmark Results

| Backend | Accuracy | Evidence | Stale Conflicts | Secret Leaks | Avg Tokens | P95 Latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active_change_digest | 100.0% | 100.0% | 0.0% | 0.0% | 28.00 | 0.003 |
| append_only_log | 0.0% | 100.0% | 100.0% | 75.0% | 57.00 | 0.004 |
| recent_window_log | 75.0% | 80.0% | 25.0% | 0.0% | 24.50 | 0.011 |

## Reproduction

```bash
python examples/benchmarks/change-control-memory/run_benchmark.py
```
