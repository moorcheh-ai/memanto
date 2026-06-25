# Release Readiness Memory Benchmark Results

| Backend | Accuracy | Avg retrieved tokens | p95 latency ms | Stale conflict rate | Secret leak rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| memanto_service | 100.0% | 9.14 | 1.3319 | 0.0% | 0.0% |
| active_release_digest | 100.0% | 9.14 | 0.0027 | 0.0% | 0.0% |
| append_only_log | 28.6% | 15.57 | 0.0035 | 28.6% | 14.3% |
| recent_window_log | 71.4% | 10.0 | 0.0044 | 14.3% | 14.3% |

`memanto_service` writes the dataset through Memanto's `MemoryWriteService` and retrieves it with `MemoryReadService` over a Moorcheh-compatible in-memory client, so the run exercises the same record formatting, status filters, and search path used by the application while remaining deterministic in CI.
The active digest is kept as a transparent baseline: keep the current release facts by topic, suppress stale handoff notes, and never retrieve synthetic secrets.
The append-only and recent-window baselines model common memory shortcuts that either over-retrieve stale state or miss older still-current constraints.
