# Memanto vs Baseline: Context Efficiency & Latency Benchmark

**Disclaimer: The results provided in this directory are simulated/illustrative and do not represent comparisons with real systems. This is a deterministic simulation harness that measures logical work delays, not real external DB connections.**

This benchmark provides a deterministic framework to evaluate the performance of `memanto` against a standard vector database memory abstraction without requiring live API keys.

## Key Findings (Simulated)
- **Latency**: In this illustrative benchmark, the Memanto stub retrieves context significantly faster than the baseline stub.
- **Token Efficiency**: The deterministic simulation shows Memanto using a fraction of the token overhead.
- **Accuracy**: The stub perfectly recalls the required user traits without hallucination in this controlled scenario.

## Reproducibility
You can run the simulated benchmark and tests using:
```bash
python3 run_benchmark.py
python3 -m unittest test_benchmark.py
```
To measure real systems, replace the `MemoryStub` in `run_benchmark.py` with actual client implementations.
