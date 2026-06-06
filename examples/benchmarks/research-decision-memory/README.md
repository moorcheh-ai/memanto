# Research Decision Memory Benchmark

This benchmark evaluates long-running research and product agents that need to
remember the current decision trail, cite the evidence that changed a decision,
and suppress stale assumptions from earlier sessions.

The scenario models a product-research agent over several planning sessions.
Early assumptions about target users, pricing, launch readiness, data handling,
and model routing are later corrected by new evidence. The benchmark asks
golden probes about the final state and scores whether each memory strategy
returns current facts without reintroducing superseded decisions or synthetic
secrets.

## Strategies

- `active_decision_digest`: Memanto-style typed digest that stores current
  decisions by slot, keeps evidence IDs, and redacts erased facts.
- `passive_graph_history`: graph-style historical state memory that keeps all
  known values unless a caller reconciles conflicts.
- `append_only_log`: raw transcript retrieval over every historical note.
- `recent_window_log`: sliding recent-window retrieval that avoids older stale
  notes but forgets older still-valid decisions.

## Metrics

- Current-fact accuracy against the golden decision state.
- Evidence coverage for required source IDs.
- Stale conflict rate when superseded assumptions appear in the answer.
- Synthetic secret leak rate.
- Retrieved token footprint.
- p95 retrieval latency in milliseconds.
- Signal/noise ratio over retrieved evidence.

## Run

No third-party dependencies are required.

```bash
python examples/benchmarks/research-decision-memory/run_benchmark.py
python examples/benchmarks/research-decision-memory/run_benchmark.py --output examples/benchmarks/research-decision-memory/results/sample_results.json --markdown examples/benchmarks/research-decision-memory/results/sample_results.md
python -m unittest discover -s examples/benchmarks/research-decision-memory -p "test_*.py"
```

## Expected Result

The active digest should retain current decisions with evidence, avoid stale
assumptions, and retrieve less context than the append-only and graph-history
baselines. The recent-window baseline should avoid many stale facts but miss
older durable decisions that are still current.
