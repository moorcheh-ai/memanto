# Incident Runbook Memory Benchmark

Dense incident-response memory with superseded runbooks, old owner state, retained early facts, and a synthetic leaked credential.

## Summary

| Backend | Retrieval accuracy | Avg retrieved tokens | p95 latency (ms) | Stale conflict rate | Secret leak rate |
|---|---:|---:|---:|---:|---:|
| active_incident_digest | 100.0% | 5.4 | 12.1 | 0.0% | 0.0% |
| append_only_log | 14.3% | 31.1 | 21.7 | 85.7% | 42.9% |
| recent_window_log | 57.1% | 8.4 | 7.5 | 0.0% | 0.0% |

## Interpretation

- `active_incident_digest` keeps only current facts per subject/key, so it avoids stale owner/runbook conflicts and redacts the synthetic credential before retrieval.
- `append_only_log` preserves every raw event, which improves auditability but bloats retrieved context and surfaces superseded facts unless another layer filters them.
- `recent_window_log` keeps context small, but it drops older facts that are still current, such as the billing-cron owner.

## Reproduce

```bash
python run_benchmark.py --output results/sample_results.json --markdown results/sample_results.md
```
