# Data Migration Cutover Memory Benchmark

Golden-evidence benchmark for resolving current facts during a stateful billing data migration cutover.

## Reproducibility Notes

- Dataset: `examples/benchmarks/data-migration-cutover-memory/data/cutover_memory_dataset.json`
- Sessions/events/probes: 5 / 20 / 8
- Judge: deterministic golden dataset matching
- Runtime mode: offline stdlib control; no API keys, network, or LLM judge
- Python: 3.14.2 (CPython)
- OS family: Windows AMD64

## Summary

| Backend | Accuracy | Evidence | Stale conflicts | Sensitive leaks | Stored tokens | Retrieved tokens | p95 read (s) | p95 write (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| memanto_active_digest | 98.9% | 100.0% | 0.0% | 0.0% | 252 | 506 | 0.0001596 | 0.0000083 |
| passive_append_only | 74.6% | 100.0% | 75.0% | 100.0% | 337 | 417 | 0.0001895 | 0.0000005 |
| recent_window | 59.1% | 56.2% | 0.0% | 0.0% | 104 | 395 | 0.0000600 | 0.0000009 |

## Probe Detail

| Backend | Probe | Accuracy | Expected evidence | Stale evidence | Sensitive leak | Top evidence |
| --- | --- | ---: | --- | --- | --- | --- |
| memanto_active_digest | P01 | 100.0% | E13 | - | - | E05, E13, E17 |
| memanto_active_digest | P02 | 100.0% | E11, E16 | - | - | E11, E14, E16 |
| memanto_active_digest | P03 | 100.0% | E05 | - | - | E05, E14, E16 |
| memanto_active_digest | P04 | 100.0% | E17 | - | - | E13, E17, E20 |
| memanto_active_digest | P05 | 91.0% | E09 | - | - | E05, E09, E18 |
| memanto_active_digest | P06 | 100.0% | E18 | - | - | E05, E11, E18 |
| memanto_active_digest | P07 | 100.0% | E15 | - | - | E09, E15, E18 |
| memanto_active_digest | P08 | 100.0% | E19 | - | - | E05, E13, E19 |
| passive_append_only | P01 | 75.0% | E13 | E01 | - | E01, E13, E17 |
| passive_append_only | P02 | 75.0% | E11, E16 | E02 | - | E02, E11, E16 |
| passive_append_only | P03 | 75.0% | E05 | E03 | - | E03, E05, E14 |
| passive_append_only | P04 | 75.0% | E17 | E04 | - | E04, E13, E17 |
| passive_append_only | P05 | 47.0% | E09 | - | MarchPilot, billing_admin, postgres:// | E03, E09, E18 |
| passive_append_only | P06 | 100.0% | E18 | - | - | E17, E18, E19 |
| passive_append_only | P07 | 75.0% | E15 | E07 | - | E07, E12, E15 |
| passive_append_only | P08 | 75.0% | E19 | E08 | - | E08, E18, E19 |
| recent_window | P01 | 9.0% | - | - | - | E17, E18, E19 |
| recent_window | P02 | 63.5% | E16 | - | - | E16, E19, E20 |
| recent_window | P03 | 0.0% | - | - | - | E15, E16, E20 |
| recent_window | P04 | 100.0% | E17 | - | - | E17, E19, E20 |
| recent_window | P05 | 0.0% | - | - | - | E18, E19, E20 |
| recent_window | P06 | 100.0% | E18 | - | - | E17, E18, E19 |
| recent_window | P07 | 100.0% | E15 | - | - | E15, E18, E19 |
| recent_window | P08 | 100.0% | E19 | - | - | E18, E19, E20 |

## Interpretation

The active digest backend retains the same source transcript boundary as the baselines, but it stores a smaller current-state memory, removes superseded evidence from retrieval, and redacts sensitive values. The append-only baseline preserves every raw observation, which improves auditability but increases retrieved tokens and stale-conflict risk. The recent-window baseline minimizes stored tokens while losing older facts that remain operationally current.
