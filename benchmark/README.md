# Memanto Benchmarking Suite

A rigorous, reproducible benchmarking framework that evaluates **Memanto** against other agentic memory frameworks across the core tension of **Accuracy vs. Resource Footprint**.

## Supported Backends

- **Memanto** (this repo) — active memory agent with serverless retrieval
- **Mem0** — popular open-source memory layer for LLM apps
- **Zep / Graphiti** — graph-based memory with temporal awareness
- **Letta** (extensible) — agent framework with memory primitives

## Metrics

| Category | Metric | Description |
|----------|--------|-------------|
| **Accuracy** | Recall@K | Fraction of relevant memories retrieved in top-K |
| **Accuracy** | MRR (Mean Reciprocal Rank) | Inverse rank of first relevant result |
| **Accuracy** | Preference Resolution Score | Correctness of inferred user preferences |
| **Resource** | Tokens per Query | Total LLM tokens consumed |
| **Resource** | p95 Latency (ms) | 95th percentile end-to-end latency |
| **Resource** | Memory Footprint (MB) | Peak resident memory during benchmark |
| **Resource** | Background CPU (%) | CPU used by background ingestion/indexing |

## Quick Start

### 1. Install Dependencies

