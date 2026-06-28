# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other dedicated agentic memory frameworks. This suite focuses on the core tension of 2026 agent infrastructure: **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** — The reference implementation (this repo)
- **Mem0** — Popular memory layer for LLM applications
- **Zep / Graphiti** — Graph-based memory with temporal reasoning
- **Letta** — Agent framework with built-in memory

## Metrics

| Category | Metric | Description |
|----------|--------|-------------|
| **Accuracy** | Recall@K | Fraction of relevant memories retrieved in top-K |
| **Accuracy** | MRR (Mean Reciprocal Rank) | Average of reciprocal ranks of first relevant result |
| **Accuracy** | Preference Resolution Score | Ability to resolve conflicting user preferences |
| **Efficiency** | Tokens per Query | Total tokens consumed (input + output) |
| **Efficiency** | Latency (p50/p95/p99) | Time to complete memory operations |
| **Efficiency** | Memory Footprint | Peak RAM usage during operations |
| **Scalability** | Throughput | Queries per second under load |

## Quick Start

### 1. Install Dependencies

