# Long-Horizon Agent Memory Benchmark

Run: `20260607T014457127413Z`

This report compares real memory backends on the same ordered event
stream. Higher accuracy and signal-to-noise are better; lower stale
conflict, token footprint, and latency are better.

| Backend | Top-1 accuracy | Top-k current recall | Stale context | Clean-context recall | Mean context tokens | Total context tokens | Signal/noise | Read p95 ms | Write p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| memanto | 40.8% | 97.5% | 80.0% | 20.0% | 319.6 | 38351 | 0.196 | 1136.5 | 1429.2 |
| mem0 | 31.7% | 96.7% | 80.0% | 20.0% | 323.3 | 38793 | 0.192 | 22.7 | 25.0 |

## Accuracy by checkpoint

| Backend | Checkpoint | Top-1 accuracy | Top-k current recall | Stale context | Clean-context recall | Mean context tokens |
|---|---:|---:|---:|---:|---:|---:|
| memanto | 8 | 100.0% | 100.0% | 0.0% | 100.0% | 316.0 |
| memanto | 16 | 41.7% | 100.0% | 100.0% | 0.0% | 318.4 |
| memanto | 24 | 20.8% | 100.0% | 100.0% | 0.0% | 321.2 |
| memanto | 32 | 29.2% | 100.0% | 100.0% | 0.0% | 321.1 |
| memanto | 48 | 12.5% | 87.5% | 100.0% | 0.0% | 321.3 |
| mem0 | 8 | 100.0% | 100.0% | 0.0% | 100.0% | 320.3 |
| mem0 | 16 | 25.0% | 100.0% | 100.0% | 0.0% | 326.1 |
| mem0 | 24 | 20.8% | 100.0% | 100.0% | 0.0% | 326.5 |
| mem0 | 32 | 0.0% | 95.8% | 100.0% | 0.0% | 322.2 |
| mem0 | 48 | 12.5% | 87.5% | 100.0% | 0.0% | 321.2 |

## Paired comparison

`memanto - mem0` Top-1 accuracy difference: **+9.2%** (95% bootstrap CI `[+0.0%, +18.3%]`, n=120).

## Reproduction

See `config.json`, `environment.json`, and `raw_traces.jsonl` in
this directory. Raw traces preserve every query, returned context,
latency measurement, and deterministic score.
