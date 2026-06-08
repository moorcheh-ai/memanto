# Memanto vs Baseline: Context Efficiency & Latency Benchmark

This benchmark evaluates the performance of `memanto` against a standard vector database memory abstraction. 

## Key Findings
- **Latency**: Memanto retrieves context significantly faster than the baseline.
- **Token Efficiency**: Memanto maintains a tight context window, using a fraction of the token overhead required by naive RAG solutions.
- **Accuracy**: Memanto perfectly recalls the required user traits without hallucination.

## Reproducibility
```bash
python3 run_benchmark.py
python3 -m unittest test_benchmark.py
```
