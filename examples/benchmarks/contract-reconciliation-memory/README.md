# Contract Reconciliation Memory Benchmark

This benchmark is a reproducible submission for bounty #639. It tests the
"accuracy vs. resource footprint" tension with a contract-negotiation agent that
must remember current commitments while suppressing stale clauses and secrets.

The scenario is intentionally small enough to audit by hand but hard for naive
memory systems:

- commitments change across five sessions
- some old terms are explicitly superseded
- several records contain synthetic secrets that must never be recalled
- probes require current facts plus evidence IDs, not just keyword matches

## What It Compares

`run_benchmark.py` evaluates three memory strategies under the same event log:

- `append_only_log`: stores everything and retrieves keyword matches
- `recent_window_log`: only keeps the most recent events
- `active_contract_ledger`: a Memanto-style typed ledger that stores current
  slots, marks superseded facts, redacts secrets, and keeps evidence

The active ledger is not a live Memanto API call. It is an offline control model
for the behavior the challenge asks us to measure: typed memory, temporal
updates, provenance, and compact retrieval. This keeps the benchmark runnable for
reviewers without credentials while still isolating the memory behavior.

## Metrics

The runner reports:

- retrieval accuracy against a golden dataset
- average retrieved token footprint
- p95 read latency in milliseconds
- stale conflict rate
- synthetic secret leak rate
- evidence coverage
- signal/noise ratio

## Run

```bash
python examples/benchmarks/contract-reconciliation-memory/run_benchmark.py
python examples/benchmarks/contract-reconciliation-memory/test_benchmark.py
```

To write fresh reports:

```bash
python examples/benchmarks/contract-reconciliation-memory/run_benchmark.py \
  --json-out examples/benchmarks/contract-reconciliation-memory/results/sample_results.json \
  --markdown-out examples/benchmarks/contract-reconciliation-memory/results/sample_results.md
```

## Sample Result

The committed sample report shows the active ledger reaching full current-fact
accuracy with zero stale conflicts and zero secret leaks, while the append-only
and recent-window baselines either leak outdated terms or forget older active
commitments.
