# Agentic Memory Showdown Benchmark

This example is a reproducible benchmark suite for
`moorcheh-ai/memanto#639`. It compares an active, typed memory strategy that
models Memanto's current-state recall against an append-only graph-style memory
baseline that preserves stale and current facts together.

The default run is intentionally offline and dependency-free so reviewers can
reproduce the benchmark without API keys. Live platform runs should use the same
dataset and report schema, with `MOORCHEH_API_KEY` for Memanto and
`MEM0_API_KEY` for Mem0 when available.

## Scenario

The fixture models a multi-session product assistant whose user preferences
change over time:

- a stale launch-update preference is replaced by a newer detailed memo style
- customer-facing timezone rules change from UTC-only to local time
- payment retry architecture decisions must remain retrievable
- investor and engineering audiences require different opening emphasis

This stresses the core #639 question: accuracy versus resource footprint when
agent memory has dense history and stale facts.

## Metrics

Each backend is evaluated on the same chronological turns and questions:

- total tokens ingested
- total tokens retrieved
- p95 retrieval latency
- retrieval accuracy, including a penalty when stale terms contaminate answers

The offline benchmark uses a deterministic token counter so relative footprint
is stable across machines.

## Reproduce

From this folder:

```bash
python -m showdown_benchmark --format markdown --output results/sample_results.md
python -m showdown_benchmark --format json --output results/sample_results.json
python tests/test_showdown_benchmark.py
```

From the repository root:

```bash
python examples/benchmarks/agentic-memory-showdown/tests/test_showdown_benchmark.py
```

## Live Run Notes

The committed sample report is the offline reproducibility baseline. To produce
a live submission-quality run, export API keys locally and add adapters that
call the actual services while preserving the same `MemoryBackend` interface:

```bash
export MOORCHEH_API_KEY="mk_..."
export MEM0_API_KEY="..."
python -m showdown_benchmark --format markdown --output results/live_results.md
```

Do not commit API keys, `.env` files, platform analytics screenshots, payment
details, or other private account data.

## PR and Social Showcase Checklist

- PR folder lives under `/examples/benchmarks/`.
- PR description includes a benchmark summary and a social media showcase link.
- Social post should explain the scenario, include the metrics table, and
  mention `@moorcheh_ai`.
- Bounty deadline is July 1st, 2026 at 11:59 PM UTC.
- Top finalists may need to submit platform analytics screenshots privately to
  verify organic reach.

Suggested short showcase draft:

```text
I built a reproducible agentic-memory showdown for Memanto vs an append-only
graph-style memory baseline. The benchmark stresses shifting preferences,
stale facts, token footprint, p95 latency, and retrieval accuracy.

Memanto's active-memory model keeps current user intent compact while the
append-only baseline retrieves stale conflicting facts. Metrics and code:
<PR link>

@moorcheh_ai
```
