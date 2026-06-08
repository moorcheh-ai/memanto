# Research Decision Memory Results

| Backend | Accuracy | Evidence | Stale Conflicts | Secret Leaks | Avg Tokens | p95 ms | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| active_decision_digest | 100.00% | 100.00% | 0.00% | 0.00% | 21.12 | 0.0036 | 100.00% |
| passive_graph_history | 50.00% | 100.00% | 50.00% | 12.50% | 30.50 | 0.0065 | 66.67% |
| append_only_log | 50.00% | 100.00% | 50.00% | 12.50% | 167.25 | 0.0881 | 12.31% |
| recent_window_log | 50.00% | 50.00% | 0.00% | 0.00% | 10.62 | 0.0024 | 100.00% |

Generated with `run_benchmark.py` using only stdlib components.
