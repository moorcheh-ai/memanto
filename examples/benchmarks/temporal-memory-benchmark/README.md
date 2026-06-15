# Temporal Memory Benchmark (Illustrative Framework)

This benchmark provides a framework to evaluate `memanto` against a baseline vector database approach for handling temporal reasoning and memory tasks. 

> [!NOTE]
> **Disclaimer:** The metrics and script provided below currently serve as **illustrative placeholders and examples** demonstrating how the benchmarking pipeline is structured. A real dataset and active API integration are required to generate live metrics.

## Metrics

We measure three primary dimensions:
1. **P95 Latency**: Total time taken to retrieve information.
2. **Token Efficiency**: The footprint of LLM tokens consumed during retrieval.
3. **Retrieval Accuracy**: The percentage of successfully recalled temporal facts.

## Example Results (Simulated Placeholder Data)

| Metric | Memanto | Baseline Vector DB |
| --- | --- | --- |
| Accuracy | 96% | 68% |
| Token Usage | 450 | 15000 |
| P95 Latency | ~0.06s | ~0.9s |

## How to reproduce the simulated framework

```bash
python benchmark.py
```
