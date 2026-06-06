# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo) — active memory agent with serverless retrieval
- **Mem0** — popular open-source memory layer for LLM apps
- **Zep / Graphiti** — graph-based memory with entity extraction
- **Letta** — agent framework with built-in memory

## Metrics

| Metric | Description | Why It Matters |
|--------|-------------|--------------|
| `recall_accuracy` | F1 score of retrieved memories vs. ground truth | Core correctness |
| `token_efficiency` | Tokens used per successful recall | Cost at scale |
| `p95_latency_ms` | 95th percentile of `recall()` latency | User experience |
| `memory_footprint_mb` | Peak RAM during benchmark | Infrastructure cost |
| `preference_resolution` | Accuracy on nuanced, preference-based queries | Production realism |

## Quick Start

