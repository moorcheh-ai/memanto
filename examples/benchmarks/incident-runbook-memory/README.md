# Incident Runbook Memory Benchmark

This benchmark evaluates the core 2026 agent-memory tradeoff from issue #639:
current-state accuracy versus retrieved-context footprint.

The scenario is an incident-response assistant that receives dense, shifting
technical notes over five sessions. Facts mutate over time: owners rotate,
runbooks are superseded, customer-facing language changes, and one raw note
contains a synthetic credential. The benchmark asks current-state questions and
scores each backend against golden answers.

## Backends

| Backend | Role |
|---|---|
| `active_incident_digest` | Memanto-style active memory that keeps the latest fact per subject/key and redacts secrets before retrieval. |
| `append_only_log` | Archive-memory control that returns every raw event for the queried subject. |
| `recent_window_log` | Short-context control that keeps only the five newest raw events. |

The two controls are deliberately simple and deterministic. They are not
published vendor scores for Mem0, Letta, Zep/Graphiti, or Hindsight. They are
included so the experimental harness, dataset, metrics, and expected behavior
can be reviewed without API keys. The same `MemoryBackend` protocol can be used
to add hosted provider adapters while preserving the dataset and evaluator.

## Metrics

The runner reports:

- retrieval accuracy against golden current facts
- total ingested tokens
- stored tokens
- average retrieved tokens
- deterministic p95 latency estimate
- stale conflict rate
- secret leak rate

Latency is modeled from scanned records and retrieved tokens so CI runs are
stable. Hosted adapters should replace that value with measured wall-clock
latency while keeping the same query set.

## Run

No runtime dependency is required beyond Python 3.10+.

```bash
python run_benchmark.py --output results/sample_results.json --markdown results/sample_results.md
```

From the repository root:

```bash
python examples/benchmarks/incident-runbook-memory/run_benchmark.py \
  --output examples/benchmarks/incident-runbook-memory/results/sample_results.json \
  --markdown examples/benchmarks/incident-runbook-memory/results/sample_results.md
```

Run the tests:

```bash
python -m unittest discover -s examples/benchmarks/incident-runbook-memory -p test_*.py
```

## Dataset Design

All backends ingest the same ordered event stream. The golden queries cover:

- a service owner that changed from `payments-oncall` to `checkout-platform-oncall`
- a checkout runbook that superseded `restart-all-pods`
- customer language that changed for `payments-ledger`
- a mitigation that changed for `catalog-worker`
- a failover region that changed from `us-east-1` to `eu-west-1`
- an early but still-current `billing-cron` owner
- a synthetic credential that must not be surfaced

This makes the benchmark stress both sides of the challenge: stale-context
avoidance and resource footprint.
