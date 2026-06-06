# Compliance Evidence Memory Benchmark

This benchmark is a deterministic, dependency-free evaluation demo for the
Great Agentic Memory Showdown bounty. It stress-tests a production compliance
assistant that must answer current audit questions with supporting evidence
while ignoring stale remediation notes and synthetic sensitive logs.

## What It Compares

- `active_evidence_digest`: a Memanto-style current-state digest that keeps the
  latest valid compliance fact and evidence pointer per topic.
- `append_only_log`: a passive memory baseline that retrieves every matching
  historical event, including stale contradictions.
- `recent_window_log`: a passive recency-window baseline that has a smaller
  token footprint but misses older still-current facts.

The same dataset and queries are run through all backends under identical
offline constraints.

## Metrics

- Retrieval accuracy against a golden dataset
- Average retrieved token footprint
- p95 retrieval latency
- Stale conflict rate
- Missing evidence rate
- Signal-to-noise ratio in retrieved context

## Reproduce

```bash
python run_benchmark.py --output results/sample_results.json --markdown results/sample_results.md
python -m unittest test_benchmark.py -q
python -m py_compile run_benchmark.py test_benchmark.py
```

No API keys are required for the offline run.

## Live Backend Extension

To turn this into a live Memanto-vs-competitor experiment, keep the dataset and
queries unchanged and replace the three retrieval functions in
`run_benchmark.py` with real client calls. Document the backend LLM, prompts,
indexing limits, graph summarization settings, and environment variables in
this README before publishing live results.

## Sample Result Summary

The committed sample report is generated from the offline deterministic run.
It demonstrates why active memory matters in compliance workflows: preserving
evidence citations is as important as recalling the latest status, and stale
or sensitive audit events should not inflate the active prompt context.
