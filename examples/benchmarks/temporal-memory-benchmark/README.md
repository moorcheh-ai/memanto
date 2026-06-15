# Temporal Memory Benchmark

This benchmark evaluates `memanto` against a baseline vector database approach for handling temporal reasoning and memory tasks. 

## Metrics

We measured three primary dimensions:
1. **P95 Latency**: Total time taken to retrieve information.
2. **Token Efficiency**: The footprint of LLM tokens consumed during retrieval.
3. **Retrieval Accuracy**: The percentage of successfully recalled temporal facts.

## Results

| Metric | Memanto | Baseline Vector DB |
| --- | --- | --- |
| Accuracy | 96% | 68% |
| Token Usage | 450 | 15000 |
| P95 Latency | ~0.06s | ~0.9s |

## How to reproduce

```bash
python benchmark.py
```
