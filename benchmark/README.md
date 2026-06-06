# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo) — active memory agent with serverless retrieval
- **Mem0** — dedicated memory platform
- **Zep / Graphiti** — graph-based memory (placeholder for community extension)
- **Hindsight** — (placeholder for community extension)
- **Letta** — (placeholder for community extension)

## Metrics

| Metric | Description |
|--------|-------------|
| `recall_accuracy` | Correctness of retrieved memories vs. ground truth |
| `token_efficiency` | Tokens used per successful recall (lower = better) |
| `p95_latency_ms` | 95th percentile end-to-end latency |
| `memory_footprint_kb` | Working set size during benchmark |
| `preference_resolution` | Ability to resolve nuanced, conflicting preferences |

## Quick Start

