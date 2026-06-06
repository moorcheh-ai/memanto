# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo)
- **Mem0** (https://github.com/mem0ai/mem0)
- **Zep/Graphiti** (https://github.com/getzep/graphiti)

## Metrics

| Metric | Description |
|--------|-------------|
| Recall Accuracy | % of correctly retrieved facts |
| Latency (p50/p95/p99) | Response time percentiles |
| Token Efficiency | Tokens used per query / per correct answer |
| Context Window Bloat | Tokens in context / relevant tokens |
| Background Processing | Async indexing latency |

## Quick Start

