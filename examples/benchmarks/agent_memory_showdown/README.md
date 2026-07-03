# Agent Memory Showdown Benchmark

This folder contains the source dataset for the Memanto Benchmarking Challenge
[#639](https://github.com/moorcheh-ai/memanto/issues/639).

Run the no-key smoke benchmark from the repository root:

```bash
python scripts/memanto_memory_benchmark.py \
  --frameworks memanto-offline,lexical-baseline \
  --dataset examples/benchmarks/agent_memory_showdown/dataset.json \
  --output benchmark-results.json
```

For live Memanto vs Mem0 runs, see
[`docs/bounty_reports/639_memanto_benchmarking_challenge.md`](../../../docs/bounty_reports/639_memanto_benchmarking_challenge.md).
