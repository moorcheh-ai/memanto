# Research Decision Memory Results

| Backend | Accuracy | Evidence | Stale Conflicts | Secret Leaks | Avg Tokens | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| active_decision_digest | 100.00% | 100.00% | 0.00% | 0.00% | 21.12 | 100.00% |
| passive_graph_history | 50.00% | 100.00% | 50.00% | 12.50% | 30.50 | 66.67% |
| append_only_log | 50.00% | 100.00% | 50.00% | 12.50% | 167.25 | 12.31% |
| recent_window_log | 50.00% | 50.00% | 0.00% | 0.00% | 10.62 | 100.00% |

Runtime-specific latency is omitted from saved sample artifacts; run the benchmark without output flags for live p95 ms.

Generated with `run_benchmark.py` using only stdlib components.
