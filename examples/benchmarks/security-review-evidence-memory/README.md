# Security Review Evidence Memory Benchmark

This benchmark is a credential-free evaluation for long-lived security review agents. It compares a Memanto-style active security digest with passive graph-style, append-only, and recent-window memory baselines.

The scenario models a security review that spans multiple sessions. Findings are opened, remediated, re-tested, downgraded, or marked false positive. The memory layer must preserve current evidence, suppress stale findings, and avoid leaking synthetic secrets that appeared in earlier audit logs.

## What It Measures

- Current-fact accuracy across sessions
- Retrieved token footprint
- p95 retrieval latency
- Stale conflict rate
- Synthetic secret leak rate
- Evidence coverage
- Signal-to-noise ratio

## Backends

| Backend | Purpose |
|---|---|
| `active_security_digest` | Memanto-style active digest that stores the latest normalized security facts and redacts secrets |
| `passive_graph_memory` | Competitor-style passive fact graph that preserves historical fact nodes without active stale-state resolution |
| `append_only_log` | Raw transcript memory that returns every historical observation |
| `recent_window_log` | Sliding-window baseline that drops older durable decisions |

## Experimental Protocol

All backends ingest the same four review sessions in the same order and answer the same six golden probes. The active digest, passive graph-style memory, append-only log, and recent-window log therefore share one dataset, one scoring function, and one metric table.

## Run

```bash
python examples/benchmarks/security-review-evidence-memory/run_benchmark.py
python examples/benchmarks/security-review-evidence-memory/run_benchmark.py --output examples/benchmarks/security-review-evidence-memory/results/sample_results.json --markdown examples/benchmarks/security-review-evidence-memory/results/sample_results.md
python -m unittest discover -s examples/benchmarks/security-review-evidence-memory -p "test_*.py"
```

No Moorcheh or Memanto credentials are required for this reviewer-safe version. The active digest is intentionally implemented as a deterministic stand-in so reviewers can validate the evaluation harness and compare memory behavior without provisioning services.

## Expected Result Shape

The active digest should score best on current-fact accuracy, stale conflict suppression, and secret safety while retrieving substantially less context than the append-only log. The passive graph-style baseline should preserve more structured evidence than a raw log, but still expose stale statuses and old sensitive facts when it does not actively reconcile current state. The recent-window baseline should avoid some old noise but miss durable decisions such as false-positive rationale.

## Bounty Fit

This targets the "Accuracy vs. Resource Footprint" challenge from [issue #639](https://github.com/moorcheh-ai/memanto/issues/639) by testing a production security-review workflow where stale evidence and secret leakage are as important as answer accuracy.
