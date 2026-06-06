# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo)
- **Mem0** (https://github.com/mem0ai/mem0)
- **Zep/Graphiti** (https://github.com/getzep/graphiti)

## Metrics

| Metric | Description |
|--------|-------------|
| `recall_accuracy` | Correctness of retrieved memories for a given query |
| `token_efficiency` | Tokens consumed per successful recall (lower is better) |
| `latency_p95_ms` | 95th percentile latency of recall operations |
| `memory_footprint_mb` | Approximate memory usage during benchmark |
| `preference_resolution` | Ability to resolve nuanced, conflicting preferences |

## Quick Start

